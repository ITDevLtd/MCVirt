#!/bin/bash

set -e
set -x

# Copy to master, as packages built on the 18.04 host fail
temp_dir=$(ssh pub-jenkins 'mktemp -d')
echo $temp_dir | grep '/tmp'
if [ "$?" != "0" ] || [ "$temp_dir" == "" ]
then
  echo bad temp dir
  exit 1
fi
rsync -havx --delete ./* ./.gi* pub-jenkins:${temp_dir}/
ssh pub-jenkins "pushd $temp_dir; ./build.sh || ./scripts/build.sh; popd"
scp pub-jenkins:"${temp_dir}/mcvirt*.deb" ./
ssh pub-jenkins "rm -rf ${temp_dir}"

rm -rf ~/mcvirt_packages/*
cp mcvirt*.deb ~/mcvirt_packages/


PROXY="http://ci-host-1.dock.studios:3128"

function node_install_pyro() {
  node="$1"

  # Setup pip-cache directory
  ssh $node 'mkdir /opt/pip-cache'
  ssh $node 'mount -t nfs 192.168.122.1:/opt/pip-cache /opt/pip-cache'

  # Create apt-get wrapper to wait for lock
  cat > ./apt-get-wait <<'EOF'
#!/bin/bash

i=0
tput sc
while fuser /var/lib/dpkg/lock >/dev/null 2>&1 ; do
    case $(($i % 4)) in
        0 ) j="-" ;;
        1 ) j="\\" ;;
        2 ) j="|" ;;
        3 ) j="/" ;;
    esac
    tput rc
    echo -en "\r[$j] Waiting for other software managers to finish..."
    sleep 0.5
    ((i=i+1))
done

/usr/bin/apt-get "$@"
EOF
  scp apt-get-wait $node:./
  ssh $node 'chmod +x ./apt-get-wait'

  # Update proxy in apt configuration
  ssh ${node} 'find /etc/apt/ -type f -exec sed -i "s/fare-proxy.dock.studios/172.16.86.12/g" {} \;'
  # Install pip (for installing Pyro and MockLdap), git (for obtianing Pyro source)
  # and pre-requisites for building MockLdap
  ssh ${node} 'apt-get update'
  ssh ${node} './apt-get-wait install python-pip git libsasl2-dev python-dev libldap2-dev libssl-dev python-coverage jq --assume-yes'
  ssh ${node} "https_proxy=${PROXY} git clone https://github.com/MatthewJohn/Pyro4"
  ssh ${node} "pushd Pyro4; http_proxy=${PROXY} https_proxy=${PROXY} pip3 install --cache-dir /opt/pip-cache ./; popd"
  ssh ${node} "http_proxy=${PROXY} https_proxy=${PROXY} pip3 install --cache-dir /opt/pip-cache MockLdap"
  # Run these again withou the 'cache-dir' option. If it's not supported, then
  # the modules will be installed, otherwise, it won't do anything
  ssh ${node} "pushd Pyro4; http_proxy=${PROXY} https_proxy=${PROXY} pip3 install ./; popd"
  ssh ${node} "http_proxy=${PROXY} https_proxy=${PROXY} pip3 install MockLdap"
}

function setup_cluster() {
  os="$1"
  nodes="$2"

  if [ "$nodes" -gt "1" ]
  then
    for itx in $(seq 2 $nodes)
    do
      ssh mcvirt-host-${itx} './apt-get-wait install drbd8-utils --assume-yes'
      ssh mcvirt-host-${itx} 'modprobe drbd'
      connect_string=$(ssh mcvirt-host-$itx 'mcvirt cluster get-connect-string --username mjc --password pass')
      ssh mcvirt-host-1 "mcvirt cluster add-node --conn $connect_string --username mjc --password pass"
    done

    # Enable DRBD
    ssh mcvirt-host-1 './apt-get-wait install drbd8-utils --assume-yes'
    ssh mcvirt-host-1 'modprobe drbd'
    ssh mcvirt-host-1 'mcvirt drbd enable --username mjc --password pass'
  else
    echo One node cluster - no setup requird
  fi
}

function setup_storage() {
  os="$1"
  nodes="$2"

  if [ "$os" == "ubuntu-1404" ]
  then
    default_vg="ubuntu-1404-vg"
  elif [ "$os" == "ubuntu-1604" ]
  then
    default_vg="ubuntu-1604-template-vg"
  elif [ "$os" == "debian-8" ]
  then
    default_vg="debian-8-template-vg"
  fi
  ssh mcvirt-host-1 "mcvirt storage create local-vg --type Lvm --volume-group-name ${default_vg} --username mjc --password pass"
  ssh mcvirt-host-1 "mcvirt network create Production --interface vmbr0 --username mjc --password pass"
}

function setup_nodes() {
  os="$1"
  nodes="$2"
  for itx in $(seq 1 $nodes)
  do
    node_name="mcvirt-host-${itx}"

    # Start the VM
    sudo start-vm $os $itx
    ssh $node_name 'killall -9 dhclient'
    #sleep 10

    # Install pyro
    node_install_pyro $node_name

    # Copy binary for installation
    scp ~/mcvirt_packages/mcvirt*.deb ${node_name}:~/

    # Install package, ignore failures as dependencies will not be
    # installed
    ssh $node_name 'dpkg -i ~/mcvirt*.deb' || true
    ssh $node_name './apt-get-wait install -f --assume-yes'
    sleep 120

    # Stop MCVirt daemons, clear config and restart - HACK due to issues with
    # starting both daemons on a new build
    ssh $node_name './apt-get-wait install --assume-yes dos2unix gawk'
    ssh $node_name "ps aux  | grep python | grep mcvirt | gawk '{ print \$2 }' | xargs kill -9" || true
    ssh $node_name 'service mcvirtd stop; service mcvirt-ns stop; rm -rf /var/lib/mcvirt/* /etc/mcvirt/* /var/lock/mcvir* /var/run/mcvirt*'
    scp ./analysis.patch ${node_name}:./
    ssh $node_name 'dos2unix /usr/local/lib/python2.7/dist-packages/Pyro4/core.py'
    ssh $node_name 'patch -p0 -d / -i /root/analysis.patch'
    ssh $node_name 'echo -e "#!/bin/bash\nMCVIRT_DEBUG=DEBUG python-coverage run --source /usr/lib/python2.7/dist-packages/mcvirt --parallel-mode --rcfile=/root/coverage_rc /usr/sbin/mcvirtd" > /usr/bin/mcvirtd'
    ssh $node_name 'echo -e "#!/bin/bash\nMCVIRT_DEBUG=DEBUG python-coverage run --source /usr/lib/python2.7/dist-packages/mcvirt --parallel-mode --rcfile=/root/coverage_rc /usr/sbin/mcvirt-ns" > /usr/bin/mcvirt-ns'
    ssh $node_name 'chmod +x /usr/bin/mcvirt-ns /usr/bin/mcvirtd'
    ssh $node_name 'systemctl daemon-reload || true'
    # Create coverage confing
    ssh $node_name 'echo -e "[run]\ndata_file = /root/coverage_data\nparallel = True\n" > /root/coverage_rc'

    # Update log to jq
    #ssh $node_name "cat /var/lib/mcvirt/${node_name}/config.json | jq '.log_level = \"DEBUG\"' > /var/lib/mcvirt/${node_name}/config.json"

    # Start daemons
    # Long sleep required for generating dh params on ubuntu 16.04
    # TODO remove sleep once locking is implemented and service start hangs until
    # it is up and running
    #ssh $node_name 'service mcvirt-ns start; sleep 20; service mcvirtd start; sleep 60'
    ssh $node_name 'service mcvirt-ns stop; service mcvirtd stop' || true
    ssh $node_name 'service mcvirt-ns start; sleep 120; service mcvirtd start; sleep 20'
    #ssh $node_name 'service mcvirt-ns start; service mcvirtd start; sleep 60' || true
    #ssh $node_name 'bash -c "/usr/sbin/mcvirt-ns &"'
    #sleep 120
    #ssh $node_name 'bash -c "/usr/sbin/mcvirtd &"'
    #sleep 120

    # Setup VM cluster IP
    ssh $node_name 'mcvirt node --set-ip-address $(hostname -i) --username mjc --password pass'
    ssh $node_name 'mkdir /var/lib/mcvirt/$(hostname)/iso'
  done
  setup_cluster $os $nodes
  setup_storage $os
}

function run_tests() {
  os="$1"
  nodes="$2"

  echo Running tests
  # Stop MCVirt on host 1
  ssh mcvirt-host-1 'service mcvirtd stop'
  ssh mcvirt-host-1 "ps aux | grep mcvirt | grep mcvirtd | grep -v grep | grep coverage | gawk '{ print \$2 }' | xargs kill -15" || true
  # Run tests with python coverage
  set -e
  ssh mcvirt-host-1 'python-coverage run --source /usr/lib/python2.7/dist-packages/mcvirt --parallel-mode --rcfile=/root/coverage_rc /usr/lib/python2.7/dist-packages/mcvirt/test/run_tests.py'
  set +e
}

function obtain_code_coverage_reports() {
  os="$1"
  nodes="$2"
  for itx in $(seq 1 $nodes)
  do
    ssh mcvirt-host-${itx} 'service mcvirtd stop; service mcvirt-ns stop' || true
    ssh mcvirt-host-${itx} "ps aux | grep mcvirt | grep usr/bin | gawk '{ print \$2 }' | xargs kill -15" || true
    # Obtain analysis
    # TODO investigate why some nodes don't generate this
    scp mcvirt-host-${itx}:./coverage_dat* ./ || true

    # Obtain debug logs
    scp mcvirt-host-${itx}:/var/log/mcvirt.log ./debug-log-${os}-${nodes}-${itx}.log
  done
}

function stop_nodes() {
  os="$1"
  nodes="$2"
  for itx in $(seq 1 $nodes)
  do
    # Stop the VM. Do not
    # stop node 1, as this is used
    # to generate coverage report
    if [ "$itx" != "1" ]
    then
      sudo stop-vm $os $itx
    fi
  done
}

function test_os() {
  os="$1"
  rm -f ~/mcvirt-known-hosts
  for cluster_size in $(seq $MIN_CLUSTER_SIZE $MAX_CLUSTER_SIZE)
  do
    {
      setup_nodes $os $cluster_size;
      run_tests $os $nodes;
      obtain_code_coverage_reports $os $cluster_size;
      stop_nodes $os $nodes;
    } || {
      obtain_code_coverage_reports $os $nodes;
      exit 1;
    }
  done
}

function start() {
  for os_type in $TEST_OPERATING_SYSTEMS
  do
    test_os $os_type
  done
}


# Generate patch file
function prepare_code_analysis() {

  # Create analysis directory if it doesn't exist
  rm -rf ./coverage_rc ./coverage_dat*

cat << 'EOF' > ./analysis.patch
--- ./etc/init.d/mcvirtd
+++ ./etc/init.d/mcvirtd
@@ -15,7 +15,7 @@
 PATH=/sbin:/usr/sbin:/bin:/usr/bin
 DESC="MCVirt daemon"
 NAME=mcvirtd
-DAEMON=/usr/sbin/$NAME
+DAEMON=/usr/bin/$NAME
 DAEMON_ARGS=""
 PIDFILE=/var/run/$NAME.pid
 SCRIPTNAME=/etc/init.d/$NAME
--- ./etc/init.d/mcvirt-ns
+++ ./etc/init.d/mcvirt-ns
@@ -15,7 +15,7 @@
 PATH=/sbin:/usr/sbin:/bin:/usr/bin
 DESC="MCVirt name server daemon"
 NAME=mcvirt-ns
-DAEMON=/usr/sbin/$NAME
+DAEMON=/usr/bin/$NAME
 DAEMON_ARGS=""
 PIDFILE=/var/run/$NAME.pid
 SCRIPTNAME=/etc/init.d/$NAME
--- ./usr/local/lib/python2.7/dist-packages/Pyro4/core.py
+++ ./usr/local/lib/python2.7/dist-packages/Pyro4/core.py
@@ -1148,9 +1148,14 @@ class Daemon(object):
                     data = []
                     for method, vargs, kwargs in vargs:
                         method = util.getAttribute(obj, method)
+                        from coverage import coverage
+                        cov = coverage(config_file='/root/coverage_rc', source='/usr/lib/python2.7/dist-packages/mcvirt')
+                        cov.start()
                         try:
                             result = method(*vargs, **kwargs)  # this is the actual method call to the Pyro object
                         except Exception:
+                            cov.stop()
+                            cov.save()
                             xt, xv = sys.exc_info()[0:2]
                             log.debug("Exception occurred while handling batched request: %s", xv)
                             xv._pyroTraceback = util.formatTraceback(detailed=Pyro4.config.DETAILED_TRACEBACK)
@@ -1160,6 +1165,8 @@ class Daemon(object):
                             break  # stop processing the rest of the batch
                         else:
                             data.append(result)
+                        cov.stop()
+                        cov.save()
                     wasBatched = True
                 else:
                     # normal single method call

--- ./usr/lib/python2.7/dist-packages/mcvirt/rpc/certificate_generator.py
+++ ./usr/lib/python2.7/dist-packages/mcvirt/rpc/certificate_generator.py
@@ -103,7 +103,7 @@ class CertificateGenerator(PyroObject):
         path = self._get_certificate_path('capriv.pem')

         if not self._ensure_exists(path, assert_raise=False):
-            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '4096'])
+            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '1024'])

         return path

@@ -151,7 +151,7 @@ class CertificateGenerator(PyroObject):
         path = self._get_certificate_path('clientkey.pem')

         if not self._ensure_exists(path, assert_raise=False):
-            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])
+            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '1024'])

         return path

@@ -195,7 +195,7 @@ class CertificateGenerator(PyroObject):
         path = self._get_certificate_path('serverkey.pem')
         if not self._ensure_exists(path, assert_raise=False):
             # Generate new SSL private key
-            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])
+            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '1024'])
         return path

     @property
@@ -208,7 +208,7 @@ class CertificateGenerator(PyroObject):
         if not self._ensure_exists(path, assert_raise=False):
             # Generate new DH parameters
             Syslogger.logger().info('Generating DH parameters file')
-            System.runCommand([self.OPENSSL, 'dhparam', '-out', path, '2048'])
+            System.runCommand([self.OPENSSL, 'dhparam', '-out', path, '1024'])
             Syslogger.logger().info('DH parameters file generated')
         return path
EOF
}

function perform_code_analysis() {
  scp ./coverage_data* mcvirt-host-1:./
  rm -f coverage_data*
  find_command='`find /usr/lib/python2.7/dist-packages/mcvirt -type f -name "*.py"`'
  ssh mcvirt-host-1 "python-coverage combine --rcfile=/root/coverage_rc"
  ssh mcvirt-host-1 "python-coverage report -m --rcfile=/root/coverage_rc $find_command"
  ssh mcvirt-host-1 "python-coverage xml --rcfile=/root/coverage_rc $find_command"
  scp mcvirt-host-1:./coverage.xml ./
  sed -i 's/filename=\"/filename=\"source/g' ./coverage.xml
}

rm -rf ./coverage_data
rm -rf ./debug-log-*.log
rm -rf coverage*.xml
prepare_code_analysis
start
perform_code_analysis

for os_type in $TEST_OPERATING_SYSTEMS
do
  echo stop_nodes $os_type 1
done


set +e

# Perform pep8 checks
rm -rf pep8_report.txt
pep8 source > pep8_report.txt || true


# Perform pylint
rm -rf pylint_report.txt

pylint --output-format=parseable --rcfile ./setup.cfg --reports=no `find -type f -name '*.py' ! -name 'build_man.py'` | tee ./pylint_report.txt


# Run sonar
cp coverage.xml coverage-sonar.xml
for i in $(find . -type f -name '*.py' | sed 's#^./##g'); do sed -i "s#$(echo $i | sed 's#source/.*/usr/lib#source/usr/lib#g')#$i#g" coverage-sonar.xml; done

branch=$(git branch -a --points-at $(git log --oneline | head -1 | tail -1 | gawk '{ print $1 }') | grep -v detached | sed 's#[ \t]*remotes/origin/##g' | grep master)
if [ "x${branch}" == "x" ]
then
  branch=$(git branch -a --points-at $(git log --oneline | head -1 | tail -1 | gawk '{ print $1 }') | grep -v detached | sed 's#[ \t]*remotes/origin/##g' | head -1)
fi
if [ "x${branch}" == "x" ]
then
  branch=$(git branch -a --points-at $(git log --oneline | head -2 | tail -1 | gawk '{ print $1 }') | grep -v detached | sed 's#[ \t]*remotes/origin/##g' | grep master)
fi
if [ "x${branch}" == "x" ]
then
  branch=$(git branch -a --points-at $(git log --oneline | head -2 | tail -1 | gawk '{ print $1 }') | grep -v detached | sed 's#[ \t]*remotes/origin/##g' | head -1)
fi

set -e

sonar-scanner \
  -Dsonar.projectKey=MCVirt \
  -Dsonar.sources=. \
  -Dsonar.host.url=http://sonarqube.dock.studios \
  -Dsonar.login=${SONAR_KEY} \
  -Dsonar.branch.name="$branch" -X


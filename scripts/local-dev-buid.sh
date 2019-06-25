#!/bin/bash

# Remove old packages
rm *.deb

# Build for both old and new branches
./scripts/build.sh
./build.sh

for i in {1..3}
do
  ssh root@mcvirt${i} 'rm -f *mcvirt*.deb'
  scp mcvirt{,-common,-daemon}_*.deb root@mcvirt${i}:~/
  ssh root@mcvirt${i} 'dpkg -i ./*mcvirt*.deb; apt-get install -f --assume-yes; echo "service mcvirt-ns restart; service mcvirtd restart"'
done

#!/bin/bash

# Remove old packages
rm *.deb

# Build for both old and new branches
./scripts/build.sh
./build.sh

if [ "x$MCVIRT_VM_PREFIX" == "x" ]
then
    MCVIRT_VM_PREFIX=mcvirt
fi
if [ "x$MCVIRT_VM_COUNT" == "x" ]
then
    MCVIRT_VM_COUNT=3
fi
if [ "x$MCVIRT_VM_USER" == "x" ]
then
    MCVIRT_VM_USER=root
fi

for i in $(seq ${MCVIRT_VM_COUNT})
do
  ssh ${MCVIRT_VM_USER}@$MCVIRT_VM_PREFIX${i} 'rm -f *mcvirt*.deb'
  scp mcvirt{,-common,-daemon}_*.deb ${MCVIRT_VM_USER}@$MCVIRT_VM_PREFIX${i}:~/
  ssh ${MCVIRT_VM_USER}@${MCVIRT_VM_PREFIX}${i} 'sudo dpkg -i ./*mcvirt*.deb; sudo apt-get install -f --assume-yes; echo "sudo service mcvirt-ns restart; sudo service mcvirtd restart"'
done

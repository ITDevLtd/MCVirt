#!/bin/bash
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#

# Get the version from git or the VERSION file
function get_version {
  if [ -d "./.git" ]
  then
    echo `git describe --dirty --always --tags --long | sed s/^v//`
  else
    echo `tr -d '\n' < VERSION`
  fi
}

VERSION=$(get_version)
ARCH=all

# Put version number into version file
echo "VERSION = '$VERSION'" >> ./source/mcvirt-common/usr/lib/python2.7/dist-packages/mcvirt/version.py

# Put version into debian control file
sed -i "s/%VERSION%/$VERSION/g" ./source/*/DEBIAN/control

for package_src in ./source/*
do
    # Build package
    name=$(echo $package_src | sed 's/\.\/source\///g')
    dpkg --build $package_src ./${name}_${VERSION}_${ARCH}.deb
done

# Remove old version number
git checkout -- ./source/usr/lib/python2.7/dist-packages/mcvirt/version.py ./source/*/DEBIAN/control

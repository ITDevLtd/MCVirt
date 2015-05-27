#!/bin/bash
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#

# Get the version from git or the VERSION file
function get_version {
  if [ -d "./.git" ]
  then
    echo `git describe --dirty --always | sed s/^v//`
  else
    echo `tr -d '\n' < VERSION`
  fi
}

VERSION=$(get_version)
ARCH=all

# Build the man documentation
python build_man.py $VERSION

# Build the package
dpkg --build ./source ./mcvirt_${VERSION}_${ARCH}.deb


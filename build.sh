#!/bin/bash
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#


VERSION=0.1
ARCH=all

# Create a temporary directory
temporary_dir=`mktemp -d`

# Perform an SVN export of the source working copy
# to ensure that .svn directories are not present
svn export source $temporary_dir/source

# Build the package
dpkg --build $temporary_dir/source ./mcvirt_${VERSION}_${ARCH}.deb

# Remove temporary directory
rm -r $temporary_dir

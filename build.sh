#!/bin/bash
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#

VERSION=0.10
ARCH=all

# Build the package
dpkg --build ./source ./mcvirt_${VERSION}_${ARCH}.deb


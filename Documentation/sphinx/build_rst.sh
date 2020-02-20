#!/bin/bash

mkdir -p src/mcvirt
cp -r ../../source/mcvirt-*/usr/lib/python3/dist-packages/mcvirt/* ./src/mcvirt
sphinx-apidoc -o ./ ./src --force
rm -rf src

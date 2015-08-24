#!/bin/bash

# Run pep8 checks
pep8

# Run pylint checks
pylint --rcfile=setup.cfg source/usr/lib/mcvirt

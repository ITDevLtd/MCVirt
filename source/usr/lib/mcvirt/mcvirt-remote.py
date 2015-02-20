#!/usr/bin/python
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#


import sys

sys.path.insert(0, '/usr/lib')

from mcvirt.mcvirt import McVirt
from cluster.remote import Remote

mcvirt_instance = McVirt()

output = Remote.receiveRemoteCommand(mcvirt_instance, sys.argv[1])

if (output is not None):
  print output


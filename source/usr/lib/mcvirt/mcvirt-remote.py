#!/usr/bin/python
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#


import sys

sys.path.insert(0, '/usr/lib')

from mcvirt.mcvirt import McVirt, McVirt
from cluster.remote import Remote

mcvirt_instance = McVirt(None, initialise_nodes=False)

end_conection = False
try:
  while True:
    data = str.strip(sys.stdin.readline())
    (output, end_conection) = Remote.receiveRemoteCommand(mcvirt_instance, data)

    sys.stdout.write("%s\n" % output)
    sys.stdout.flush()

    if (end_conection):
      break
except Exception, e:
  mcvirt_instance.getClusterObject().tearDown()
  mcvirt_instance = None
  raise e

mcvirt_instance.getClusterObject().tearDown()
mcvirt_instance = None

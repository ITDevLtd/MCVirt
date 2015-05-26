#!/usr/bin/python
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#


import sys

sys.path.insert(0, '/usr/lib')

from mcvirt.mcvirt import MCVirt
from cluster.remote import Remote

mcvirt_instance = MCVirt(None, initialise_nodes=False)

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
    mcvirt_instance = None
    raise Exception, e, sys.exc_info()[2]

mcvirt_instance = None

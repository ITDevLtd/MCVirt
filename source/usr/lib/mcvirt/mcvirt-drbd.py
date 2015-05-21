#!/usr/bin/python
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#


import sys
import os
import syslog

sys.path.insert(0, '/usr/lib')

from mcvirt.node.drbd import DRBDSocket

# Obtain DRBD resource name from argument
drbd_resource = os.environ['DRBD_RESOURCE']

# Determine if DRBD socket exists
if (os.path.exists(DRBDSocket.SOCKET_PATH)):
  import socket

  # Connect to socket and send DRBD resource name to be set as out-of-sync
  socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

  socket.connect(DRBDSocket.SOCKET_PATH)
  socket.send(drbd_resource)
  socket.close()
else:
  from mcvirt.mcvirt import McVirt
  from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory

  # Otherwise, create an McVirt object and update the VM directly
  mcvirt_instance = McVirt()
  hard_drive_object = HardDriveFactory.getDrbdObjectByResourceName(mcvirt_instance, drbd_resource)
  hard_drive_object.setSyncState(False)
  mcvirt_instance = None

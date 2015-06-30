#!/usr/bin/python
# Copyright (c) 2014 - I.T. Dev Ltd
#
# This file is part of MCVirt.
#
# MCVirt is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# MCVirt is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/>

import sys
import os

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
    from mcvirt.mcvirt import MCVirt
    from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory

    # Otherwise, create an MCVirt object and update the VM directly
    mcvirt_instance = MCVirt(obtain_lock=True, initialise_nodes=False)
    hard_drive_object = HardDriveFactory.getDrbdObjectByResourceName(
        mcvirt_instance,
        drbd_resource
    )
    hard_drive_object.setSyncState(False, update_remote=False)
    mcvirt_instance = None

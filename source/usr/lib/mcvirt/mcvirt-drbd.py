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
import json

sys.path.insert(0, '/usr/lib')

from mcvirt.client.rpc import Connection  # noqa
from mcvirt.constants import DirectoryLocation  # noqa

# Obtain Drbd resource name from argument
drbd_resource = os.environ['DRBD_RESOURCE']

# Determine sync state from arguments
sync_state = bool(int(sys.argv[1])) if len(sys.argv) > 1 else False

# Ensure that the hook config exists
if not os.path.exists(DirectoryLocation.DRBD_HOOK_CONFIG):
    sys.exit(0)

# Read the hook config
with open(DirectoryLocation.DRBD_HOOK_CONFIG, 'r') as fh:
    config = json.load(fh)

# Create RPC connection and obtain hard drive factory
rpc = Connection(username=config['username'], password=config['password'])
hard_drive_factory = rpc.get_connection('hard_drive_factory')

# Obtain hard drive object and set sync state
hard_drive_object = hard_drive_factory.getDrbdObjectByResourceName(
    drbd_resource
)
rpc.annotate_object(hard_drive_object)
hard_drive_object.setSyncState(sync_state, update_remote=True)

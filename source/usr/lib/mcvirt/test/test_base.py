# Copyright (c) 2016 - I.T. Dev Ltd
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

import unittest

from mcvirt.client.rpc import Connection
from mcvirt.parser import Parser
from mcvirt.constants import PowerStates, LockStates


def skip_drbd(required):

    def wrapper_gen(f):

        def wrapper(*args):
            if (bool(args[0].rpc.get_connection('node_drbd').is_enabled()) !=
                    bool(wrapper.required)):
                return unittest.skip(('DRBD either required and not available or'
                                      ' can\'t be present and is installed.'))

        wrapper.required = wrapper_gen.required
        return wrapper

    wrapper_gen.required = required
    return wrapper_gen


class TestBase(unittest.TestCase):
    """Provide base test case, with constructor/destructor
    for providing access to the parser and RPC
    """

    def setUp(self):
        """Obtain connections to the daemon and create various
        member variables.
        """
        # Define RPC credentials, which are the default superuser credentials
        # that are supplied with MCVirt
        self.RPC_USERNAME = 'mjc'
        self.RPC_PASSWORD = 'pass'

        # Create and store RPC connection to daemon.
        self.rpc = Connection(self.RPC_USERNAME, self.RPC_PASSWORD)

        # Create and store parser instance
        self.parser = Parser(verbose=False)

        # Obtain the session ID from the RPC connection and re-use this,
        # so that the parser does not need to authenticate with a password
        self.parser.parse_arguments('list --username %s --password %s' % (self.RPC_USERNAME,
                                                                          self.RPC_PASSWORD))
        Parser.USERNAME = self.RPC_USERNAME
        Parser.SESSION_ID = self.rpc.session_id

    def tearDown(self):
        """Destroy stored objects."""
        self.rpc = None
        self.parser = None

    def stop_and_delete(self, vm_name):
        """Stop and remove a virtual machine"""
        virtual_machine_factory = self.rpc.get_connection('virtual_machine_factory')

        if virtual_machine_factory.check_exists(vm_name):
            vm_object = virtual_machine_factory.getVirtualMachineByName(vm_name)
            self.rpc.annotate_object(vm_object)

            # Reset sync state for any Drbd disks
            for disk_object in vm_object.getHardDriveObjects():
                self.rpc.annotate_object(disk_object)
                if disk_object.get_type() == 'Drbd':
                    disk_object.setSyncState(True)

            if not vm_object.isRegistered():
                # Manually register VM on local node
                vm_object.register()

            # Stop the VM if it is running
            if vm_object.getPowerState() == PowerStates.RUNNING.value:
                vm_object.stop()

            if vm_object.getLockState() is LockStates.LOCKED.value:
                vm_object.setLockState(LockStates.UNLOCKED.value)

            # Delete VM
            vm_object.delete(True)

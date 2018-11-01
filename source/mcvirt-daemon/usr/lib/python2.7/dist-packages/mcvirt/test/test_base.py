# pylint: disable=C0103
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
from mcvirt.utils import get_hostname


def skip_drbd(required):
    """Skip DRBD wrapper"""

    def wrapper_gen(f):
        """Wrapper method call"""

        # Disable docstring check, as this will override the docstring
        # used for the test
        def wrapper(*args):  # pylint: disable=C0111
            if (bool(args[0].rpc.get_connection('node_drbd').is_enabled()) !=
                    bool(wrapper.required)):
                return args[0].skipTest(('DRBD either required and not available or'
                                         ' can\'t be present and is installed.'))

        wrapper.required = wrapper_gen.required
        return wrapper

    wrapper_gen.required = required
    return wrapper_gen


class TestBase(unittest.TestCase):
    """Provide base test case, with constructor/destructor
    for providing access to the parser and RPC
    """

    # Define RPC credentials, which are the default superuser credentials
    # that are supplied with MCVirt
    RPC_USERNAME = 'mjc'
    RPC_PASSWORD = 'pass'

    @classmethod
    def setUpClass(cls):
        """Obtain connections to the daemon and create various
        member variables.
        """
        # Create and store RPC connection to daemon.
        cls.rpc = Connection(cls.RPC_USERNAME, cls.RPC_PASSWORD)

        # Create and store parser instance
        cls.parser = Parser(verbose=False)

        # Obtain the session ID from the RPC connection and re-use this,
        # so that the parser does not need to authenticate with a password
        # self.parser.parse_arguments('list --username %s --password %s' % (self.RPC_USERNAME,
        #                                                                   self.RPC_PASSWORD))

        cls.parser.username = cls.RPC_USERNAME
        cls.parser.session_id = cls.rpc.session_id

        # Setup variable for test VM
        cls.test_vms = \
            {
                'TEST_VM_1':
                {
                    'name': 'mcvirt-unittest-vm',
                    'cpu_count': 1,
                    'memory_allocation': '100MB',
                    'memory_allocation_bytes': 100000000,
                    'disk_size': ['100MiB'],
                    'disk_size_bytes': [104857600],
                    'networks': ['Production']
                },
                'TEST_VM_2':
                {
                    'name': 'mcvirt-unittest-vm2',
                    'cpu_count': 2,
                    'memory_allocation': '120MiB',
                    'memory_allocation_bytes': 125829120,
                    'disk_size': ['25.6MB'],
                    'disk_size_bytes': [25600000],
                    'networks': ['Production']
                }
            }

        # Ensure any test VM is stopped and removed from the machine
        cls.stop_and_delete(cls.test_vms['TEST_VM_2']['name'])
        cls.stop_and_delete(cls.test_vms['TEST_VM_1']['name'])

        cls.vm_factory = cls.rpc.get_connection('virtual_machine_factory')

        cls.test_network_name = 'testnetwork'
        cls.test_physical_interface = 'vmbr0'
        cls.network_factory = cls.rpc.get_connection('network_factory')

        # Determine if the test network exists. If so, delete it
        if cls.network_factory.check_exists(cls.test_network_name):
            network = cls.network_factory.get_network_by_name(cls.test_network_name)
            cls.rpc.annotate_object(network)
            network.delete()

    def tearDown(self):
        """Tear down test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        self.rpc.ignore_drbd()
        self.stop_and_delete(self.test_vms['TEST_VM_2']['name'])
        self.stop_and_delete(self.test_vms['TEST_VM_1']['name'])

    @classmethod
    def tearDownClass(cls):
        """Destroy stored objects."""
        cls.rpc.ignore_drbd()

        # Remove the test network, if it exists
        if cls.network_factory.check_exists(cls.test_network_name):
            network = cls.network_factory.get_network_by_name(cls.test_network_name)
            cls.rpc.annotate_object(network)
            network.delete()

        cls.network_factory = None
        cls.vm_factory = None
        cls.rpc = None
        cls.parser = None

    def create_vm(self, vm_name, storage_type):
        """Create a test VM, annotate object and ensure it exists"""
        all_nodes = self.rpc.get_connection('cluster').get_nodes(include_local=True)
        available_nodes = self.rpc.get_connection('cluster').get_nodes(include_local=False)

        # If the number of nodes in the cluster does not match the
        # specific storage type, use the local host and add remote nodes
        # as necessary
        if len(all_nodes) > 2 and storage_type == 'Drbd':
            available_nodes = [get_hostname(), available_nodes[0]]
        elif len(all_nodes) > 1 and storage_type == 'Local':
            available_nodes = [get_hostname()]
        else:
            available_nodes = all_nodes

        vm_object = self.vm_factory.create(self.test_vms[vm_name]['name'],
                                           self.test_vms[vm_name]['cpu_count'],
                                           self.test_vms[vm_name]['memory_allocation'],
                                           self.test_vms[vm_name]['disk_size'],
                                           self.test_vms[vm_name]['networks'],
                                           storage_type=storage_type,
                                           available_nodes=available_nodes)
        self.rpc.annotate_object(vm_object)
        self.assertTrue(self.vm_factory.check_exists_by_name(self.test_vms[vm_name]['name']))
        return vm_object

    @classmethod
    def stop_and_delete(cls, vm_name):
        """Stop and remove a virtual machine"""
        virtual_machine_factory = cls.rpc.get_connection('virtual_machine_factory')

        if virtual_machine_factory.check_exists_by_name(vm_name):
            vm_object = virtual_machine_factory.get_virtual_machine_by_name(vm_name)
            cls.rpc.annotate_object(vm_object)

            # Reset sync state for any Drbd disks
            for disk_object in vm_object.get_hard_drive_objects():
                cls.rpc.annotate_object(disk_object)
                if disk_object.get_type() == 'Drbd':
                    disk_object.setSyncState(True)

            if not vm_object.isRegistered():
                # Manually register VM on local node
                vm_object.register()

            # Stop the VM if it is running
            if vm_object.get_power_state() == PowerStates.RUNNING.value:
                vm_object.stop()

            if vm_object.getLockState() is LockStates.LOCKED.value:
                vm_object.setLockState(LockStates.UNLOCKED.value)

            if vm_object.get_delete_protection_state():
                vm_object.disable_delete_protection(vm_name[::-1])

            # Delete VM
            vm_object.delete()

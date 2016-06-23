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

import unittest

from mcvirt.parser import Parser
from mcvirt.mcvirt import MCVirt
from mcvirt.virtual_machine.virtual_machine import VirtualMachine, PowerStates
from mcvirt.virtual_machine.network_adapter import NetworkAdapterDoesNotExistException


def stopAndDelete(mcvirt_connection, vm_name):
    """Stops and removes VMs"""
    if (VirtualMachine._check_exists(mcvirt_connection.getLibvirtConnection(), vm_name)):
        vm_object = VirtualMachine(mcvirt_connection, vm_name)
        if (vm_object.getState() is PowerStates.RUNNING):
            vm_object.stop()
        vm_object.delete(True)


class UpdateTests(unittest.TestCase):
    """Provides unit tests for the functionality
       provided by the update subparser"""

    @staticmethod
    def suite():
        """Returns a test suite"""
        suite = unittest.TestSuite()
        suite.addTest(UpdateTests('test_remove_network'))
        suite.addTest(UpdateTests('test_remove_network_non_existant'))
        return suite

    def setUp(self):
        """Creates various objects and deletes any test VMs"""
        # Create MCVirt parser object
        self.parser = Parser(print_status=False)

        # Get an MCVirt instance
        self.mcvirt = MCVirt()

        # Setup variable for test VM
        self.test_vm = \
            {
                'name': 'mcvirt-unittest-vm',
                'cpu_count': '1',
                'disks': ['100'],
                'memory_allocation': '100',
                'networks': ['Production']
            }

        # Ensure any test VM is stopped and removed from the machine
        stopAndDelete(self.mcvirt, self.test_vm['name'])

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        stopAndDelete(self.mcvirt, self.test_vm['name'])
        self.mcvirt = None

    def test_remove_network(self):
        """Removes a network interface from a VM, using the
           parser"""
        # Create test VM
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vm['name'],
            self.test_vm['cpu_count'],
            self.test_vm['memory_allocation'],
            self.test_vm['disks'],
            self.test_vm['networks'])

        # Obtain the MAC address of the network interface
        # attached to the new VM
        mac_address = test_vm_object.getNetworkObjects()[0].getMacAddress()

        # Ensure there is 1 network adapter attached to the VM
        self.assertEqual(len(test_vm_object.getNetworkObjects()), 1)

        # Remove the network interface from the VM, using the argument
        # parser
        self.parser.parse_arguments('update %s --remove-network %s' % (self.test_vm['name'],
                                                                       mac_address),
                                    mcvirt_instance=self.mcvirt)

        # Ensure there is no longer any network adapters attached to the VM
        self.assertEqual(len(test_vm_object.getNetworkObjects()), 0)

    def test_remove_network_non_existant(self):
        """Attempts to remove a network interface from a VM
           that doesn't exist"""
        # Create test VM
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vm['name'],
            self.test_vm['cpu_count'],
            self.test_vm['memory_allocation'],
            self.test_vm['disks'],
            self.test_vm['networks'])

        # Ensure there is 1 network adapter attached to the VM
        self.assertEqual(len(test_vm_object.getNetworkObjects()), 1)

        # Remove the network interface from the VM, using the argument
        # parser
        with self.assertRaises(NetworkAdapterDoesNotExistException):
            self.parser.parse_arguments('update %s --remove-network 11:11:11:11:11:11' %
                                        self.test_vm['name'],
                                        mcvirt_instance=self.mcvirt)

        # Ensure that the network adapter is still attached to the VM
        self.assertEqual(len(test_vm_object.getNetworkObjects()), 1)

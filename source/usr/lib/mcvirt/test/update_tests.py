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

from mcvirt.test.test_base import TestBase
from mcvirt.exceptions import NetworkAdapterDoesNotExistException


class UpdateTests(TestBase):
    """Provide unit tests for the functionality
    provided by the update subparser
    """

    @staticmethod
    def suite():
        """Return a test suite"""
        suite = unittest.TestSuite()
        suite.addTest(UpdateTests('test_remove_network'))
        suite.addTest(UpdateTests('test_remove_network_non_existant'))
        suite.addTest(UpdateTests('test_set_windows_flag'))
        return suite

    def setUp(self):
        """Create network adapter factory"""
        super(UpdateTests, self).setUp()
        self.network_adapter_factory = self.rpc.get_connection('network_adapter_factory')

    def tearDown(self):
        """Tear down network adapter factory"""
        self.network_adapter_factory = None
        super(UpdateTests, self).tearDown()

    def test_remove_network(self):
        """Remove a network interface from a VM, using the
        parser
        """
        # Create test VM
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        # Obtain the MAC address of the network interface
        # attached to the new VM
        network_adapters = self.network_adapter_factory.getNetworkAdaptersByVirtualMachine(
            test_vm_object
        )
        self.rpc.annotate_object(network_adapters[0])
        mac_address = network_adapters[0].getMacAddress()

        # Ensure there is 1 network adapter attached to the VM
        self.assertEqual(len(network_adapters), 1)

        # Remove the network interface from the VM, using the argument
        # parser
        self.parser.parse_arguments('update %s --remove-network %s' %
                                    (self.test_vms['TEST_VM_1']['name'], mac_address))

        network_adapters = self.network_adapter_factory.getNetworkAdaptersByVirtualMachine(
            test_vm_object
        )
        # Ensure there is no longer any network adapters attached to the VM
        self.assertEqual(len(network_adapters), 0)

    def test_remove_network_non_existant(self):
        """Attempt to remove a network interface from a VM
        that doesn't exist
        """
        # Create test VM
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        # Ensure there is 1 network adapter attached to the VM
        network_adapters = self.network_adapter_factory.getNetworkAdaptersByVirtualMachine(
            test_vm_object
        )
        self.assertEqual(len(network_adapters), 1)

        # Remove the network interface from the VM, using the argument
        # parser
        with self.assertRaises(NetworkAdapterDoesNotExistException):
            self.parser.parse_arguments('update %s --remove-network 11:11:11:11:11:11' %
                                        self.test_vms['TEST_VM_1']['name'])

        # Ensure that the network adapter is still attached to the VM
        network_adapters = self.network_adapter_factory.getNetworkAdaptersByVirtualMachine(
            test_vm_object
        )
        self.assertEqual(len(network_adapters), 1)

    def test_set_windows_flag(self):
        """Set the Windows CPU flag and check the XML is modified correctly"""
        # Create test VM
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        # Obtain VM XML
        vm_factory = self.RPC_DAEMON.DAEMON.registered_factories['virtual_machine_factory']
        vm = vm_factory.getVirtualMachineByName('mcvirt-unittest-vm')
        xml = vm.getLibvirtConfig()

        # Check that <cpu> section is not in XML by default
        self.assertEqual(xml.find('./cpu'), None)

        # Set Windows CPU flag
        self.parser.parse_arguments('update %s --add-flag windows' %
                                    self.test_vms['TEST_VM_1']['name'])

        xml = vm.getLibvirtConfig()

        # Check CPU section exists
        cpu_section = xml.find('./cpu')
        self.assertTrue(cpu_section is not None)
        self.assertEquals(cpu_section.get('mode'), 'custom')
        self.assertEquals(cpu_section.get('match'), 'exact')

        # Check mode section exists
        model_section = cpu_section.find('./model')
        self.assertTrue(model_section is not None)
        self.assertEquals(model_section.get('fallback'), 'allow')
        self.assertEquals(model_section.text, 'core2duo')

        # Check feature section exists
        feature_section = cpu_section.find('./feature')
        self.assertTrue(feature_section is not None)
        self.assertEquals(feature_section.get('policy'), 'require')
        self.assertEquals(feature_section.get('name'), 'nx')

        # Unset Windows flag
        self.parser.parse_arguments('update %s --remove-flag windows' %
                                    self.test_vms['TEST_VM_1']['name'])

        # Check that <cpu> section is now not present
        xml = vm.getLibvirtConfig()
        self.assertEqual(xml.find('./cpu'), None)

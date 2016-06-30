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

from mcvirt.exceptions import (NetworkDoesNotExistException, NetworkUtilizedException,
                               NetworkAlreadyExistsException)
from mcvirt.test.test_base import TestBase


class NetworkTests(TestBase):
    """Test suite for performing tests on the network class"""

    @staticmethod
    def suite():
        """Return a test suite of the network tests"""
        suite = unittest.TestSuite()
        suite.addTest(NetworkTests('test_create'))
        suite.addTest(NetworkTests('test_duplicate_name_create'))
        suite.addTest(NetworkTests('test_delete'))
        suite.addTest(NetworkTests('test_delete_non_existent'))
        suite.addTest(NetworkTests('test_delete_utilized'))
        suite.addTest(NetworkTests('test_list'))

        return suite

    def test_create(self):
        """Test the creation of network through the argument parser"""
        # Ensure network does not exist
        self.assertFalse(self.network_factory.check_exists(self.test_network_name))

        # Create network using parser
        self.parser.parse_arguments('network create %s --interface=%s' %
                                    (self.test_network_name,
                                     self.test_physical_interface))

        # Ensure network exists
        self.assertTrue(self.network_factory.check_exists(self.test_network_name))

        # Obtain network object
        network_object = self.network_factory.get_network_by_name(self.test_network_name)
        self.rpc.annotate_object(network_object)

        # Ensure the name is correct
        self.assertEqual(network_object.get_name(), self.test_network_name)

        # Remove test network
        network_object.delete()

    def test_duplicate_name_create(self):
        """Test attempting to create a network with a duplicate name through the argument parser"""
        # Create network
        self.network_factory.create(self.test_network_name, self.test_physical_interface)

        # Attempt to create a network with the same name
        with self.assertRaises(NetworkAlreadyExistsException):
            self.parser.parse_arguments('network create %s --interface=%s' %
                                        (self.test_network_name,
                                         self.test_physical_interface))

        # Delete test network
        network_object = self.network_factory.get_network_by_name(self.test_network_name)
        self.rpc.annotate_object(network_object)
        network_object.delete()

    def test_delete(self):
        """Test deleting a network through the argument parser"""
        # Create network
        self.network_factory.create(self.test_network_name, self.test_physical_interface)

        # Remove the network through the argument parser
        self.parser.parse_arguments('network delete %s' %
                                    self.test_network_name)

        # Ensure the network no longer exists
        self.assertFalse(self.network_factory.check_exists(self.test_network_name))

    def test_delete_non_existent(self):
        """Attempt to delete a non-existent network"""
        # Ensure the network does not exist
        self.assertFalse(self.network_factory.check_exists(self.test_network_name))

        # Attempt to remove the network using the argument parser
        with self.assertRaises(NetworkDoesNotExistException):
            self.parser.parse_arguments('network delete %s' %
                                        self.test_network_name)

    def test_delete_utilized(self):
        """Attempt to remove a network that is in use by a VM"""
        # Create test network and create test VM connected to the network
        self.network_factory.create(self.test_network_name, self.test_physical_interface)
        self.vm_factory.create(self.test_vms['TEST_VM_1']['name'], 1, 100, [100],
                               [self.test_network_name], storage_type='Local')

        # Attempt to remove the network
        with self.assertRaises(NetworkUtilizedException):
            self.parser.parse_arguments('network delete %s' %
                                        self.test_network_name)

    def test_list(self):
        """Attempt to use the parser to list the networks"""
        # Run the network list, to ensure an exception is not thrown
        self.parser.parse_arguments('network list')

        # Create test network and re-run network list
        self.network_factory.create(self.test_network_name, self.test_physical_interface)
        self.parser.parse_arguments('network list')

        # Run the network list to ensure that the table contains the name
        # and the physical interface of the test network
        list_output = self.network_factory.get_network_list_table()
        self.assertTrue(self.test_network_name in list_output)
        self.assertTrue(self.test_physical_interface in list_output)

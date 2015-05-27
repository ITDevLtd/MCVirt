#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest
import sys

from mcvirt.parser import Parser
from mcvirt.mcvirt import MCVirt, MCVirtException
from mcvirt.node.network import Network, NetworkDoesNotExistException, NetworkAlreadyExistsException, NetworkUtilizedException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine

def stopAndDelete(test_object):
    """Stops and removes test objects"""
    # Determine if the test VM is present and remove it if it is
    if (VirtualMachine._checkExists(test_object.mcvirt.getLibvirtConnection(), test_object.test_vm_name)):
        vm_object = VirtualMachine(test_object.mcvirt, test_object.test_vm_name)
        if (vm_object.getState()):
            vm_object.stop()
        vm_object.delete(True)

    # Remove any test networks
    if (Network._checkExists(test_object.test_network_name)):
        network_object = Network(test_object.mcvirt, test_object.test_network_name)
        network_object.delete()


class NetworkTests(unittest.TestCase):
    """Test suite for performing tests on the network class"""

    @staticmethod
    def suite():
        """Returns a test suite of the network tests"""
        suite = unittest.TestSuite()
        suite.addTest(NetworkTests('test_create'))
        suite.addTest(NetworkTests('test_duplicate_name_create'))
        suite.addTest(NetworkTests('test_delete'))
        suite.addTest(NetworkTests('test_delete_non_existent'))
        suite.addTest(NetworkTests('test_delete_utilized'))

        return suite

    def setUp(self):
        """Creates various objects"""
        # Create MCVirt parser object
        self.parser = Parser(print_status=False)

        # Get an MCVirt instance
        self.mcvirt = MCVirt()
        self.test_network_name = 'test_network'
        self.test_physical_interface = 'vmbr99'

        # Setup variable for test VM
        self.test_vm_name = 'mcvirt-unittest-vm'

        stopAndDelete(self)

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        stopAndDelete(self)
        self.mcvirt = None

    def test_create(self):
        """Tests the creation of network through the argument parser"""
        # Ensure network does not exist
        self.assertFalse(Network._checkExists(self.test_network_name))

        # Create network using parser
        self.parser.parse_arguments('network create %s --interface=%s' % (self.test_network_name, self.test_physical_interface), mcvirt_instance=self.mcvirt)

        # Ensure network exists
        self.assertTrue(Network._checkExists(self.test_network_name))

        # Obtain network object
        network_object = Network(self.mcvirt, self.test_network_name)

        # Ensure the name is correct
        self.assertEqual(network_object.getName(), self.test_network_name)

        # Remove test network
        network_object.delete()

    def test_duplicate_name_create(self):
        """Test attempting to create a network with a duplicate name through the argument parser"""
        # Create network
        Network.create(self.mcvirt, self.test_network_name, self.test_physical_interface)

        # Attempt to create a network with the same name
        with self.assertRaises(NetworkAlreadyExistsException):
            self.parser.parse_arguments('network create %s --interface=%s' % (self.test_network_name, self.test_physical_interface), mcvirt_instance=self.mcvirt)

        # Delete test network
        network_object = Network(self.mcvirt, self.test_network_name)
        network_object.delete()

    def test_delete(self):
        """Test deleting a network through the argument parser"""
        # Create network
        Network.create(self.mcvirt, self.test_network_name, self.test_physical_interface)

        # Remove the network through the argument parser
        self.parser.parse_arguments('network delete %s' % self.test_network_name, mcvirt_instance=self.mcvirt)

        # Ensure the network no longer exists
        self.assertFalse(Network._checkExists(self.test_network_name))

    def test_delete_non_existent(self):
        """Attempt to delete a non-existent network"""
        # Ensure the network does not exist
        self.assertFalse(Network._checkExists(self.test_network_name))

        # Attempt to remove the network using the argument parser
        with self.assertRaises(NetworkDoesNotExistException):
            self.parser.parse_arguments('network delete %s' % self.test_network_name, mcvirt_instance=self.mcvirt)

    def test_delete_utilized(self):
        """Attempt to remove a network that is in use by a VM"""
        # Create test network and create test VM connected to the network
        Network.create(self.mcvirt, self.test_network_name, self.test_physical_interface)
        test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], [self.test_network_name])

        # Attempt to remove the network
        with self.assertRaises(NetworkUtilizedException):
            self.parser.parse_arguments('network delete %s' % self.test_network_name, mcvirt_instance=self.mcvirt)

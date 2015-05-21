#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest

from mcvirt.parser import Parser
from mcvirt.mcvirt import McVirt, McVirtException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine

def stopAndDelete(mcvirt_connection, vm_name):
  """Stops and removes VMs"""
  if (VirtualMachine._checkExists(mcvirt_connection.getLibvirtConnection(), vm_name)):
    vm_object = VirtualMachine(mcvirt_connection, vm_name)
    if (vm_object.getState()):
      vm_object.stop()
    vm_object.delete(True)


class AuthTests(unittest.TestCase):
  """Provides unit tests for the VirtualMachine class"""

  @staticmethod
  def suite():
    """Returns a test suite of the Virtual Machine tests"""
    suite = unittest.TestSuite()
    suite.addTest(AuthTests('test_add_user'))
    suite.addTest(AuthTests('test_remove_user'))
    return suite

  def setUp(self):
    """Creates various objects and deletes any test VMs"""
    # Create McVirt parser object
    self.parser = Parser(print_status=False)

    # Get an McVirt instance
    self.mcvirt = McVirt()

    # Setup variable for test VM
    self.test_vm = \
    {
      'name': 'mcvirt-unittest-vm',
      'cpu_count': '1',
      'disks': ['100'],
      'memory_allocation': '100',
      'networks': ['Production']
    }

    self.test_user = 'test_user'

    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm['name'])

  def tearDown(self):
    """Stops and tears down any test VMs"""
    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm['name'])
    self.mcvirt = None

  def test_add_user(self):
    """Adds a user to a virtual machine, using the argument parser"""
    # Ensure VM does not exist
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm['name'], self.test_vm['cpu_count'],
                                           self.test_vm['memory_allocation'], self.test_vm['disks'],
                                           self.test_vm['networks'])
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm['name']))

    # Ensure user is not in 'user' group
    auth_object = self.mcvirt.getAuthObject()
    self.assertFalse(self.test_user in auth_object.getUsersInPermissionGroup('user', test_vm_object))

    # Add user to 'user' group using parser
    self.parser.parse_arguments('permission --add-user %s %s' % (self.test_user, self.test_vm['name']),
                                mcvirt_instance=self.mcvirt)

    # Ensure VM exists
    self.assertTrue(self.test_user in auth_object.getUsersInPermissionGroup('user', test_vm_object))

  def test_remove_user(self):
    """Removes a user from a virtual machine, using the argument parser"""
    # Ensure VM does not exist
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm['name'], self.test_vm['cpu_count'],
                                           self.test_vm['memory_allocation'], self.test_vm['disks'],
                                           self.test_vm['networks'])
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm['name']))

    # Add user to 'user' group and ensure they have been added
    auth_object = self.mcvirt.getAuthObject()
    auth_object.addUserPermissionGroup(self.mcvirt, 'user', self.test_user, test_vm_object)
    self.assertTrue(self.test_user in auth_object.getUsersInPermissionGroup('user', test_vm_object))

    # Remove user from 'user' group using parser
    self.parser.parse_arguments('permission --delete-user %s %s' % (self.test_user, self.test_vm['name']),
                                mcvirt_instance=self.mcvirt)

    # Ensure user is no longer in 'user' group
    self.assertFalse(self.test_user in auth_object.getUsersInPermissionGroup('user', test_vm_object))

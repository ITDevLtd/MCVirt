#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest
import sys

sys.path.insert(0, '/usr/lib')

from mcvirt.parser import Parser
from mcvirt.mcvirt import McVirt
from mcvirt.virtual_machine.virtual_machine import VirtualMachine

def stopAndDelete(mcvirt_connection, vm_name):
  """Stops and removes VMs"""
    if (VirtualMachine._checkExists(mcvirt_connection.getLibvirtConnection(), vm_name)):
      vm_object = VirtualMachine(mcvirt_connection, vm_name)
      if (vm_object.isRunning()):
        vm_object.stop()
      vm_object.delete(True)

class VirtualMachineTests(unittest.TestCase):

  def setUp(self):
    """Creates various objects and deletes any test VMs"""
    # Create McVirt parser object
    self.parser = Parser()

    # Get an McVirt instance
    self.mcvirt = McVirt()
    self.test_vm_name = 'unittest-test-vm'

    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm_name)

  def tearDown(self):
    """Stops and tears down any test VMs"""
    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm_name)

  def testCreate(self):
    """Tests the creation of VMs through the argument parser"""
    # Ensure VM does not exist
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    cpu_count = '1'
    disk_size = '100'
    memory_allocation = '100'
    network_name = 'Production'

    # Create virtual machine using parser
    self.parser.parse_arguments('create %s' % self.test_vm_name +
      ' --cpu-count %s --disk-size %s --memory %s --network %s' %
      (cpu_count, disk_size, memory_allocation, network_name))

    # Ensure VM exists
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

  def testStart(self):
    """Tests starting VMs through the argument parser"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Use argument parser to start the VM
    self.parser.parse_arguments('start %s' % self.test_vm_name)

    # Ensure that it is running
    self.assertTrue(test_vm_object.isRunning())

  def testStop(self):
    """Tests stopping VMs through the argument parser"""
    # Create virtual machine for testing
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Start VM and ensure it is running
    test_vm_object.start()
    self.assertTrue(test_vm_object.isRunning())

    # Use the argument parser to stop the VM
    self.parser.parse_arguments('stop %s' % self.test_vm_name)

    # Ensure the VM is stopped
    self.assertFalse(test_vm_object.isRunning())

if __name__ == '__main__':
  unittest.main()
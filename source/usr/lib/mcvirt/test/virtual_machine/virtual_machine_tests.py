#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest
import sys
import os
import shutil

sys.path.insert(0, '/usr/lib')

from mcvirt.parser import Parser
from mcvirt.mcvirt import McVirt, McVirtException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine, InvalidVirtualMachineName, VmAlreadyExistsException, VmDirectoryAlreadyExists, VmAlreadyStarted, VmAlreadyStopped

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

    # Setup variable for test VM
    self.cpu_count = '1'
    self.disk_size = '100'
    self.memory_allocation = '100'
    self.network_name = 'Production'

    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm_name)

  def tearDown(self):
    """Stops and tears down any test VMs"""
    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vm_name)

  def test_create(self):
    """Tests the creation of VMs through the argument parser"""
    # Ensure VM does not exist
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Create virtual machine using parser
    self.parser.parse_arguments('create %s' % self.test_vm_name +
      ' --cpu-count %s --disk-size %s --memory %s --network %s' %
      (self.cpu_count, self.disk_size, self.memory_allocation, self.network_name))

    # Ensure VM exists
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Obtain VM object
    vm_object = VirtualMachine(self.mcvirt, self.test_vm_name)

    # Check each of the attributes for VM
    self.assertEqual(int(vm_object.getRAM()), int(self.memory_allocation) * 1024)
    self.assertEqual(vm_object.getCPU(), self.cpu_count)

  def test_invalid_name(self):
    """Attempts to create a virtual machine with an invalid name"""
    invalid_vm_name = 'invalid.name+'

    # Ensure VM does not exist
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), invalid_vm_name))

    # Attempt to create VM and ensure exception is thrown
    with self.assertRaises(InvalidVirtualMachineName):
      self.parser.parse_arguments('create "%s"' % invalid_vm_name +
        ' --cpu-count %s --disk-size %s --memory %s --network %s' %
        (self.cpu_count, self.disk_size, self.memory_allocation, self.network_name))

    # Ensure VM has not been created
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), invalid_vm_name))

  def test_create_duplicate(self):
    """Attempts to create two VMs with the same name"""
    # Create Virtual machine
    original_memory_allocation = 200
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, original_memory_allocation, [100], ['Production'])
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Attempt to create VM with duplicate name, ensuring that an exception is thrown
    with self.assertRaises(VmAlreadyExistsException):
      VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Ensure original VM already exists
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Check memory amount of VM matches original VM
    self.assertEqual(int(test_vm_object.getRAM()), int(original_memory_allocation))

    # Remove test VM
    test_vm_object.delete(True)

  def test_vm_directory_already_exists(self):
    """Attempts to create a VM whilst the directory for the VM already exists"""
    # Create the directory for the VM
    os.makedirs(VirtualMachine.getVMDir(self.test_vm_name))

    # Attempt to create VM, expecting an exception for the directory already existing
    with self.assertRaises(VmDirectoryAlreadyExists):
      VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Ensure the VM has not been created
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Remove directory
    shutil.rmtree(VirtualMachine.getVMDir(self.test_vm_name))

  def test_start(self):
    """Tests starting VMs through the argument parser"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Use argument parser to start the VM
    self.parser.parse_arguments('start %s' % self.test_vm_name)

    # Ensure that it is running
    self.assertTrue(test_vm_object.isRunning())

  def test_start_running_vm(self):
    """Attempts to start a running VM"""
    # Create Virtual machine and start it
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])
    test_vm_object.start()

    # Use argument parser to start the VM
    with self.assertRaises(VmAlreadyStarted):
      self.parser.parse_arguments('start %s' % self.test_vm_name)

  def test_stop(self):
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

  def test_stop_stopped_vm(self):
    """Attempts to stop an already stopped VM"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Use argument parser to start the VM
    with self.assertRaises(VmAlreadyStopped):
      self.parser.parse_arguments('stop %s' % self.test_vm_name)

if __name__ == '__main__':
  unittest.main()
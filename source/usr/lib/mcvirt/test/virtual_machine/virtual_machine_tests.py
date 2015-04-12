#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest
import sys
import os
import shutil

from mcvirt.parser import Parser
from mcvirt.mcvirt import McVirt, McVirtException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine, InvalidVirtualMachineNameException, VmAlreadyExistsException, VmDirectoryAlreadyExistsException, VmAlreadyStartedException, VmAlreadyStoppedException
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode

def stopAndDelete(mcvirt_instance, vm_name):
  """Stops and removes VMs"""
  if (VirtualMachine._checkExists(mcvirt_instance.getLibvirtConnection(), vm_name)):
    vm_object = VirtualMachine(mcvirt_instance, vm_name)
    if (vm_object.isRegisteredRemotely()):
      from mcvirt.cluster.cluster import Cluster
      cluster = Cluster(mcvirt_instance)
      remote_node = vm_object.getNode()

      # Stop the VM if it is running
      if (vm_object.getState()):
        remote_node.runRemoteCommand('virtual_machine-stop',
                                     {'vm_name': test_vm_object.getName()})
      # Remove VM from remote node
      remote_node.runRemoteCommand('virtual_machine-unregister',
                                 {'vm_name': test_vm_object.getName()})
      vm_object._setNode()

      # Manually register VM on local node
      vm_object.register()

      # Delete VM
      vm_object.delete(True)
    else:
      if (vm_object.getState()):
        vm_object.stop()
      vm_object.delete(True)


class VirtualMachineTests(unittest.TestCase):
  """Provides unit tests for the VirtualMachine class"""

  @staticmethod
  def suite():
    """Returns a test suite of the Virtual Machine tests"""
    suite = unittest.TestSuite()
    suite.addTest(VirtualMachineTests('test_create_local'))
    suite.addTest(VirtualMachineTests('test_delete_local'))
    suite.addTest(VirtualMachineTests('test_invalid_name'))
    suite.addTest(VirtualMachineTests('test_create_duplicate'))
    suite.addTest(VirtualMachineTests('test_vm_directory_already_exists'))
    suite.addTest(VirtualMachineTests('test_start_local'))
    suite.addTest(VirtualMachineTests('test_start_running_vm'))
    suite.addTest(VirtualMachineTests('test_stop_local'))
    suite.addTest(VirtualMachineTests('test_stop_stopped_vm'))

    # Add tests for DRBD
    suite.addTest(VirtualMachineTests('test_create_drbd'))
    suite.addTest(VirtualMachineTests('test_delete_drbd'))
    suite.addTest(VirtualMachineTests('test_start_drbd'))
    suite.addTest(VirtualMachineTests('test_stop_drbd'))
    suite.addTest(VirtualMachineTests('test_create_drbd_not_enabled'))
    suite.addTest(VirtualMachineTests('test_add_hard_drive_drbd_not_enabled'))
    suite.addTest(VirtualMachineTests('test_offline_migrate'))

    return suite

  def setUp(self):
    """Creates various objects and deletes any test VMs"""
    # Create McVirt parser object
    self.parser = Parser(print_status=False)

    # Get an McVirt instance
    self.mcvirt = McVirt()
    self.test_vm_name = 'mcvirt-unittest-vm'

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
    self.mcvirt = None

  def test_create_local(self):
    """Perform the test_create test with Local storage"""
    self.test_create('Local')

  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_create_drbd(self):
    """Perform the test_create test with DRBD storage"""
    self.test_create('DRBD')

  def test_create(self, storage_type):
    """Tests the creation of VMs through the argument parser"""
    # Ensure VM does not exist
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Create virtual machine using parser
    self.parser.parse_arguments('create %s' % self.test_vm_name +
      ' --cpu-count %s --disk-size %s --memory %s --network %s --storage-type %s' %
      (self.cpu_count, self.disk_size, self.memory_allocation, self.network_name, storage_type),
      mcvirt_instance=self.mcvirt)

    # Ensure VM exists
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Obtain VM object
    vm_object = VirtualMachine(self.mcvirt, self.test_vm_name)

    # Check each of the attributes for VM
    self.assertEqual(int(vm_object.getRAM()), int(self.memory_allocation) * 1024)
    self.assertEqual(vm_object.getCPU(), self.cpu_count)

  @unittest.skipIf(NodeDRBD.isEnabled(),
                   'DRBD is enabled on this node')
  def test_create_drbd_not_enabled(self):
    """Attempt to create a VM with DRBD storage on a node that doesn't have DRBD enabled"""
    # Attempt to create VM and ensure exception is thrown
    with self.assertRaises(DRBDNotEnabledOnNode):
      self.parser.parse_arguments('create "%s"' % self.test_vm_name +
                                  ' --cpu-count %s --disk-size %s --memory %s --network %s --storage-type %s' %
                                  (self.cpu_count, self.disk_size, self.memory_allocation, self.network_name, 'DRBD'),
                                  mcvirt_instance=self.mcvirt)

  def test_delete_local(self):
    """Perform the test_delete test with Local storage"""
    self.test_delete('Local')

  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_delete_drbd(self):
    """Perform the test_delete test with DRBD storage"""
    self.test_delete('DRBD')

  def test_delete(self, storage_type):
    """Tests the deletion of a VM through the argument parser"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, self.cpu_count, self.memory_allocation,
                                           [self.disk_size], [self.network_name], storage_type=storage_type)
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Remove VM using parser
    self.parser.parse_arguments('delete %s --remove-data' % self.test_vm_name, mcvirt_instance=self.mcvirt)

    # Ensure VM has been deleted
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))


  def test_invalid_name(self):
    """Attempts to create a virtual machine with an invalid name"""
    invalid_vm_name = 'invalid.name+'

    # Ensure VM does not exist
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), invalid_vm_name))

    # Attempt to create VM and ensure exception is thrown
    with self.assertRaises(InvalidVirtualMachineNameException):
      self.parser.parse_arguments('create "%s"' % invalid_vm_name +
        ' --cpu-count %s --disk-size %s --memory %s --network %s --storage-type %s' %
        (self.cpu_count, self.disk_size, self.memory_allocation, self.network_name, 'Local'),
        mcvirt_instance=self.mcvirt)

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
      VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'], storage_type='Local')

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
    with self.assertRaises(VmDirectoryAlreadyExistsException):
      VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Ensure the VM has not been created
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

    # Remove directory
    shutil.rmtree(VirtualMachine.getVMDir(self.test_vm_name))

  def test_start_local(self):
    """Perform the test_start test with Local storage"""
    self.test_start('Local')

  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_start_drbd(self):
    """Perform the test_start test with DRBD storage"""
    self.test_start('DRDB')

  def test_start(self, storage_type):
    """Tests starting VMs through the argument parser"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'], storage_type='Local')

    # Use argument parser to start the VM
    self.parser.parse_arguments('start %s' % self.test_vm_name, mcvirt_instance=self.mcvirt)

    # Ensure that it is running
    self.assertTrue(test_vm_object.getState())

  def test_start_running_vm(self):
    """Attempts to start a running VM"""
    # Create Virtual machine and start it
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])
    test_vm_object.start()

    # Use argument parser to start the VM
    with self.assertRaises(VmAlreadyStartedException):
      self.parser.parse_arguments('start %s' % self.test_vm_name, mcvirt_instance=self.mcvirt)

  def test_stop_local(self):
    """Perform the test_stop test with Local storage"""
    self.test_stop('Local')

  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_stop_drbd(self):
    """Perform the test_stop test with DRBD storage"""
    self.test_stop('DRBD')

  def test_stop(self, storage_type):
    """Tests stopping VMs through the argument parser"""
    # Create virtual machine for testing
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'], storage_type=storage_type)

    # Start VM and ensure it is running
    test_vm_object.start()
    self.assertTrue(test_vm_object.getState())

    # Use the argument parser to stop the VM
    self.parser.parse_arguments('stop %s' % self.test_vm_name, mcvirt_instance=self.mcvirt)

    # Ensure the VM is stopped
    self.assertFalse(test_vm_object.getState())

  def test_stop_stopped_vm(self):
    """Attempts to stop an already stopped VM"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, 1, 100, [100], ['Production'])

    # Use argument parser to start the VM
    with self.assertRaises(VmAlreadyStoppedException):
      self.parser.parse_arguments('stop %s' % self.test_vm_name, mcvirt_instance=self.mcvirt)


  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_offline_migrate(self):
    from mcvirt.virtual_machine.hard_drive.drbd import DrbdDiskState
    from mcvirt.cluster.cluster import Cluster
    import time
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vm_name, self.cpu_count, self.memory_allocation,
                                           [self.disk_size], [self.network_name], storage_type='DRBD')

    # Get the first available remote node for the VM
    node_name = test_vm_object._getRemoteNodes()[0]

    # Assert that the VM is registered locally
    self.assertTrue(test_vm_object.isRegisteredLocally())

    # Monitor the hard drives until they are synced
    for disk_object in test_vm_object.getDiskObjects():
      while (disk_object._drbdGetDiskState() != (DrbdDiskState.UP_TO_DATE, DrbdDiskState.UP_TO_DATE)):
        time.sleep(5)

    # Migrate VM to remote node
    test_vm_object.offlineMigrate(node_name)

    # Ensure the VM node matches the destination node
    self.assertEqual(test_vm_object.getNode(), node_name)

    cluster_instance = Cluster(self.mcvirt)
    remote_node = cluster_instance.getRemoteNode(node_name)

    # Attempt to start the VM on the remote node
    remote_node.runRemoteCommand('virtual_machine-start',
                                 {'vm_name': test_vm_object.getName()})

    # Ensure VM is running
    self.assertTrue(test_vm_object.getState())

    # Attempt to stop the VM on the remote node
    remote_node.runRemoteCommand('virtual_machine-stop',
                                 {'vm_name': test_vm_object.getName()})

    # Ensure VM is stopped
    self.assertFalse(test_vm_object.getState())

    # Manually unregister VM from remote node
    remote_node.runRemoteCommand('virtual_machine-unregister',
                                 {'vm_name': test_vm_object.getName()})
    test_vm_object._setNode(None)

    # Manually register VM on local node
    test_vm_object.register()

    # Delete VM
    test_vm_object.delete(True)

    # Ensure VM no longer exists
    self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vm_name))

#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import unittest
import os
import time

from mcvirt.test.virtual_machine.virtual_machine_tests import stopAndDelete
from mcvirt.node.drbd import DRBD as NodeDRBD
from mcvirt.virtual_machine.hard_drive.drbd import DrbdConnectionState, DrbdVolumeNotInSyncException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.parser import Parser
from mcvirt.mcvirt import McVirt
from mcvirt.system import System

class DrbdTests(unittest.TestCase):
  """Provides unit tests for the DRBD hard drive class"""

  @staticmethod
  def suite():
    """Returns a test suite of the Virtual Machine tests"""
    suite = unittest.TestSuite()
    suite.addTest(DrbdTests('test_verify'))

    return suite

  def setUp(self):
    """Creates various objects and deletes any test VMs"""
    # Create McVirt parser object
    self.parser = Parser(print_status=False)

    # Get an McVirt instance
    self.mcvirt = McVirt()

    # Setup variable for test VM
    self.test_vms = \
    {
      'TEST_VM_1': \
      {
        'name': 'mcvirt-unittest-vm',
        'cpu_count': 1,
        'memory_allocation': 100,
        'disk_size': [100],
        'networks': ['Production']
      }
    }

    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])

  def tearDown(self):
    """Stops and tears down any test VMs"""
    # Ensure any test VM is stopped and removed from the machine
    stopAndDelete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])
    self.mcvirt = None

  @unittest.skipIf(not NodeDRBD.isEnabled(),
                   'DRBD is not enabled on this node')
  def test_verify(self):
    """Test the DRBD verification for both in-sync and out-of-sync DRBD volumes"""
    # Create Virtual machine
    test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vms['TEST_VM_1']['name'], self.test_vms['TEST_VM_1']['cpu_count'],
                                           self.test_vms['TEST_VM_1']['memory_allocation'], self.test_vms['TEST_VM_1']['disk_size'],
                                           self.test_vms['TEST_VM_1']['networks'], storage_type='DRBD')
    self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(), self.test_vms['TEST_VM_1']['name']))

    # Wait until the DRBD resource is synced
    for disk_object in test_vm_object.getDiskObjects():
      wait_timeout = 6
      while (disk_object._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
        # If the DRBD volume has not connected within 1 minute, throw an exception
        if (not wait_timeout):
          raise DrbdVolumeNotInSyncException('Wait for DRBD connection timed out')

        time.sleep(10)
        wait_timeout -= 1

    # Perform verification on VM, using the argument parser
    self.parser.parse_arguments('verify --vm %s' % self.test_vms['TEST_VM_1']['name'], mcvirt_instance=self.mcvirt)

    # Ensure the disks are in-sync
    for disk_object in test_vm_object.getDiskObjects():
      self.assertTrue(disk_object._isInSync())

    # Obtain the DRBD raw volume for the VM and write random data to it
    for disk_object in test_vm_object.getDiskObjects():
      raw_logical_volume_name = disk_object.getConfigObject()._getLogicalVolumeName(disk_object.getConfigObject().DRBD_RAW_SUFFIX)
      System.runCommand(['dd', 'if=/dev/urandom', 'of=%s' % disk_object.getConfigObject()._getLogicalVolumePath(raw_logical_volume_name),
                         'bs=1M', 'count=8'])
      System.runCommand(['sync'])

    # Perform another verification and ensure that an exception is raised
    with self.assertRaises(DrbdVolumeNotInSyncException):
      self.parser.parse_arguments('verify --vm %s' % self.test_vms['TEST_VM_1']['name'], mcvirt_instance=self.mcvirt)

    # Attempt to start the VM, ensuring an exception is raised
    with self.assertRaises(DrbdVolumeNotInSyncException):
      test_vm_object.start()


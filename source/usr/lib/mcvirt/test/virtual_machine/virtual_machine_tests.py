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
import os
import shutil
import xml.etree.ElementTree as ET

from mcvirt.parser import Parser
from mcvirt.mcvirt import MCVirt, MCVirtException
from mcvirt.virtual_machine.virtual_machine import (VirtualMachine,
                                                    PowerStates,
                                                    InvalidVirtualMachineNameException,
                                                    VmAlreadyExistsException,
                                                    VmDirectoryAlreadyExistsException,
                                                    VmAlreadyStartedException,
                                                    VmAlreadyStoppedException,
                                                    CannotStartClonedVmException,
                                                    CannotDeleteClonedVmException,
                                                    CannotCloneDrbdBasedVmsException,
                                                    VirtualMachineLockException)
from mcvirt.node.network import NetworkDoesNotExistException
from mcvirt.virtual_machine.hard_drive.drbd import DrbdStateException
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode
from mcvirt.test.common import stop_and_delete


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
        suite.addTest(VirtualMachineTests('test_reset'))
        suite.addTest(VirtualMachineTests('test_reset_stopped_vm'))
        suite.addTest(VirtualMachineTests('test_lock'))
        suite.addTest(VirtualMachineTests('test_stop_local'))
        suite.addTest(VirtualMachineTests('test_stop_stopped_vm'))
        suite.addTest(VirtualMachineTests('test_clone_local'))
        suite.addTest(VirtualMachineTests('test_duplicate_local'))
        suite.addTest(VirtualMachineTests('test_unspecified_storage_type_local'))
        suite.addTest(VirtualMachineTests('test_invalid_network_name'))
        suite.addTest(VirtualMachineTests('test_create_alternative_driver'))

        # Add tests for DRBD
        suite.addTest(VirtualMachineTests('test_create_drbd'))
        suite.addTest(VirtualMachineTests('test_delete_drbd'))
        suite.addTest(VirtualMachineTests('test_start_drbd'))
        suite.addTest(VirtualMachineTests('test_stop_drbd'))
        suite.addTest(VirtualMachineTests('test_create_drbd_not_enabled'))
        suite.addTest(VirtualMachineTests('test_offline_migrate'))
        suite.addTest(VirtualMachineTests('test_clone_drbd'))
        suite.addTest(VirtualMachineTests('test_duplicate_drbd'))
        suite.addTest(VirtualMachineTests('test_unspecified_storage_type_drbd'))

        return suite

    def setUp(self):
        """Creates various objects and deletes any test VMs"""
        # Create MCVirt parser object
        self.parser = Parser(print_status=False)

        # Get an MCVirt instance
        self.mcvirt = MCVirt()

        # Setup variable for test VM
        self.test_vms = \
            {
                'TEST_VM_1':
                {
                    'name': 'mcvirt-unittest-vm',
                    'cpu_count': 1,
                    'memory_allocation': 100,
                    'disk_size': [100],
                    'networks': ['Production']
                },
                'TEST_VM_2':
                {
                    'name': 'mcvirt-unittest-vm2',
                    'cpu_count': 2,
                    'memory_allocation': 120,
                    'disk_size': [100],
                    'networks': ['Production']
                }
            }

        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_2']['name'])
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_2']['name'])
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])
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
        self.assertFalse(
            VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                        self.test_vms['TEST_VM_1']['name']))

        # Create virtual machine using parser
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_1']['cpu_count'],
                                     self.test_vms['TEST_VM_1']['disk_size'][0],
                                     self.test_vms['TEST_VM_1']['memory_allocation']) +
                                    ' --network %s --storage-type %s' %
                                    (self.test_vms['TEST_VM_1']['networks'][0],
                                     storage_type),
                                    mcvirt_instance=self.mcvirt)

        # Ensure VM exists
        self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                                    self.test_vms['TEST_VM_1']['name']))

        # Obtain VM object
        vm_object = VirtualMachine(self.mcvirt, self.test_vms['TEST_VM_1']['name'])

        # Check each of the attributes for VM
        self.assertEqual(int(vm_object.getRAM()),
                         self.test_vms['TEST_VM_1']['memory_allocation'] * 1024)
        self.assertEqual(vm_object.getCPU(), str(self.test_vms['TEST_VM_1']['cpu_count']))

        # Ensure second VM does not exist
        self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                                     self.test_vms['TEST_VM_2']['name']))

        # Create second VM
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_2']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_2']['cpu_count'],
                                     self.test_vms['TEST_VM_2']['disk_size'][0],
                                     self.test_vms['TEST_VM_2']['memory_allocation']) +
                                    ' --network %s --storage-type %s' %
                                    (self.test_vms['TEST_VM_2']['networks'][0],
                                     storage_type),
                                    mcvirt_instance=self.mcvirt)

        # Ensure VM exists
        self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                                    self.test_vms['TEST_VM_2']['name']))

        # Obtain VM object
        vm_object_2 = VirtualMachine(self.mcvirt, self.test_vms['TEST_VM_2']['name'])
        vm_object_2.delete(True)

    @unittest.skipIf(NodeDRBD.isEnabled(),
                     'DRBD is enabled on this node')
    def test_create_drbd_not_enabled(self):
        """Attempt to create a VM with DRBD storage on a node that doesn't have DRBD enabled"""
        # Attempt to create VM and ensure exception is thrown
        with self.assertRaises(DRBDNotEnabledOnNode):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0], 'DRBD'),
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
        test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vms['TEST_VM_1']['name'],
                                               self.test_vms['TEST_VM_1']['cpu_count'],
                                               self.test_vms['TEST_VM_1']['memory_allocation'],
                                               self.test_vms['TEST_VM_1']['disk_size'],
                                               self.test_vms['TEST_VM_1']['networks'],
                                               storage_type=storage_type)
        self.assertTrue(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                                    self.test_vms['TEST_VM_1']['name']))

        # Remove VM using parser
        self.parser.parse_arguments('delete %s --remove-data' % self.test_vms['TEST_VM_1']['name'],
                                    mcvirt_instance=self.mcvirt)

        # Ensure VM has been deleted
        self.assertFalse(VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                                     self.test_vms['TEST_VM_1']['name']))

    def test_clone_local(self):
        """Tests the VM cloning in MCVirt using the argument parser"""
        # Create Virtual machine
        test_vm_parent = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='Local')

        test_data = os.urandom(8)

        # Obtain the disk path for the VM and write random data to it
        for disk_object in test_vm_parent.getDiskObjects():
            fh = open(disk_object.getConfigObject()._getDiskPath(), 'w')
            fh.write(test_data)
            fh.close()

        # Clone VM
        self.parser.parse_arguments(
            'clone --template %s %s' %
            (self.test_vms['TEST_VM_1']['name'],
             self.test_vms['TEST_VM_2']['name']),
            mcvirt_instance=self.mcvirt)
        test_vm_clone = VirtualMachine(self.mcvirt, self.test_vms['TEST_VM_2']['name'])

        # Check data is present on target VM
        for disk_object in test_vm_clone.getDiskObjects():
            fh = open(disk_object.getConfigObject()._getDiskPath(), 'r')
            self.assertEqual(fh.read(8), test_data)
            fh.close()

        # Attempt to start clone
        test_vm_clone.start()

        # Attempt to stop clone
        test_vm_clone.stop()

        # Attempt to start parent
        with self.assertRaises(CannotStartClonedVmException):
            test_vm_parent.start()

        # Attempt to delete parent
        with self.assertRaises(CannotDeleteClonedVmException):
            test_vm_parent.delete(True)

        # Remove clone
        test_vm_clone.delete(True)

        # Remove parent
        test_vm_parent.delete(True)

    @unittest.skipIf(not NodeDRBD.isEnabled(),
                     'DRBD is not enabled on this node')
    def test_clone_drbd(self):
        """Attempts to clone a DRBD-based VM"""
        # Create parent VM
        test_vm_parent = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='DRBD')

        # Attempt to clone VM
        with self.assertRaises(CannotCloneDrbdBasedVmsException):
            self.parser.parse_arguments(
                'clone --template %s %s' %
                (self.test_vms['TEST_VM_1']['name'],
                 self.test_vms['TEST_VM_2']['name']),
                mcvirt_instance=self.mcvirt)

        test_vm_parent.delete(True)

    def test_duplicate_local(self):
        """Performs test_duplicate test with Local storage"""
        self.test_duplicate('Local')

    @unittest.skipIf(not NodeDRBD.isEnabled(),
                     'DRBD is not enabled on this node')
    def test_duplicate_drbd(self):
        """Performs the test_duplicate test with DRBD storage"""
        self.test_duplicate('DRBD')

    def test_duplicate(self, storage_type):
        """Attempts to duplicate a VM using the argument parser and perform tests
           on the parent and duplicate VM"""
        # Create Virtual machine
        test_vm_parent = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='Local')

        test_data = os.urandom(8)

        # Obtain the disk path for the VM and write random data to it
        for disk_object in test_vm_parent.getDiskObjects():
            fh = open(disk_object.getConfigObject()._getDiskPath(), 'w')
            fh.write(test_data)
            fh.close()

        # Clone VM
        self.parser.parse_arguments(
            'duplicate --template %s %s' %
            (self.test_vms['TEST_VM_1']['name'],
             self.test_vms['TEST_VM_2']['name']),
            mcvirt_instance=self.mcvirt)
        test_vm_duplicate = VirtualMachine(self.mcvirt, self.test_vms['TEST_VM_2']['name'])

        # Check data is present on target VM
        for disk_object in test_vm_duplicate.getDiskObjects():
            fh = open(disk_object.getConfigObject()._getDiskPath(), 'r')
            self.assertEqual(fh.read(8), test_data)
            fh.close()

        # Attempt to start clone
        test_vm_duplicate.start()

        # Attempt to stop clone
        test_vm_duplicate.stop()

        # Start parent
        test_vm_parent.start()

        # Stop parent
        test_vm_parent.stop()

        # Remove parent
        test_vm_parent.delete(True)

        # Remove duplicate
        test_vm_duplicate.delete(True)

    def test_invalid_name(self):
        """Attempts to create a virtual machine with an invalid name"""
        invalid_vm_name = 'invalid.name+'

        # Ensure VM does not exist
        self.assertFalse(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                invalid_vm_name))

        # Attempt to create VM and ensure exception is thrown
        with self.assertRaises(InvalidVirtualMachineNameException):
            self.parser.parse_arguments(
                'create "%s"' %
                invalid_vm_name +
                ' --cpu-count %s --disk-size %s --memory %s --network %s --storage-type %s' %
                (self.test_vms['TEST_VM_1']['cpu_count'],
                 self.test_vms['TEST_VM_1']['disk_size'][0],
                 self.test_vms['TEST_VM_1']['memory_allocation'],
                 self.test_vms['TEST_VM_1']['networks'][0],
                 'Local'),
                mcvirt_instance=self.mcvirt)

        # Ensure VM has not been created
        self.assertFalse(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                invalid_vm_name))

    def test_create_duplicate(self):
        """Attempts to create two VMs with the same name"""
        # Create Virtual machine
        original_memory_allocation = 200
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            1,
            original_memory_allocation,
            [100],
            ['Production'])
        self.assertTrue(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vms['TEST_VM_1']['name']))

        # Attempt to create VM with duplicate name, ensuring that an exception is thrown
        with self.assertRaises(VmAlreadyExistsException):
            VirtualMachine.create(
                self.mcvirt,
                self.test_vms['TEST_VM_1']['name'],
                self.test_vms['TEST_VM_1']['cpu_count'],
                self.test_vms['TEST_VM_1']['memory_allocation'],
                self.test_vms['TEST_VM_1']['disk_size'],
                self.test_vms['TEST_VM_1']['networks'],
                storage_type='Local')

        # Ensure original VM already exists
        self.assertTrue(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vms['TEST_VM_1']['name']))

        # Check memory amount of VM matches original VM
        self.assertEqual(int(test_vm_object.getRAM()), int(original_memory_allocation))

        # Remove test VM
        test_vm_object.delete(True)

    def test_vm_directory_already_exists(self):
        """Attempts to create a VM whilst the directory for the VM already exists"""
        # Create the directory for the VM
        os.makedirs(VirtualMachine.getVMDir(self.test_vms['TEST_VM_1']['name']))

        # Attempt to create VM, expecting an exception for the directory already existing
        with self.assertRaises(VmDirectoryAlreadyExistsException):
            VirtualMachine.create(
                self.mcvirt,
                self.test_vms['TEST_VM_1']['name'],
                self.test_vms['TEST_VM_1']['cpu_count'],
                self.test_vms['TEST_VM_1']['memory_allocation'],
                self.test_vms['TEST_VM_1']['disk_size'],
                self.test_vms['TEST_VM_1']['networks'])

        # Ensure the VM has not been created
        self.assertFalse(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vms['TEST_VM_1']['name']))

        # Remove directory
        shutil.rmtree(VirtualMachine.getVMDir(self.test_vms['TEST_VM_1']['name']))

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
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='Local')

        # Use argument parser to start the VM
        self.parser.parse_arguments(
            'start %s' %
            self.test_vms['TEST_VM_1']['name'],
            mcvirt_instance=self.mcvirt)

        # Ensure that it is running
        self.assertTrue(test_vm_object.getState() is PowerStates.RUNNING)

    def test_start_running_vm(self):
        """Attempts to start a running VM"""
        # Create Virtual machine and start it
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'])
        test_vm_object.start()

        # Use argument parser to start the VM
        with self.assertRaises(VmAlreadyStartedException):
            self.parser.parse_arguments(
                'start %s' %
                self.test_vms['TEST_VM_1']['name'],
                mcvirt_instance=self.mcvirt)

    def test_reset(self):
        """Resets a running VM"""
        # Create Virtual machine and start it
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'])
        test_vm_object.start()

        # Use argument parser to reset the VM
        self.parser.parse_arguments(
            'reset %s' %
            self.test_vms['TEST_VM_1']['name'],
            mcvirt_instance=self.mcvirt)

    def test_reset_stopped_vm(self):
        """Attempts to reset a stopped VM"""
        # Create Virtual machine and start it
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'])

        # Use argument parser to reset the VM
        with self.assertRaises(VmAlreadyStoppedException):
            self.parser.parse_arguments(
                'reset %s' %
                self.test_vms['TEST_VM_1']['name'],
                mcvirt_instance=self.mcvirt)

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
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type=storage_type)

        # Start VM and ensure it is running
        test_vm_object.start()
        self.assertTrue(test_vm_object.getState() is PowerStates.RUNNING)

        # Use the argument parser to stop the VM
        self.parser.parse_arguments(
            'stop %s' %
            self.test_vms['TEST_VM_1']['name'],
            mcvirt_instance=self.mcvirt)

        # Ensure the VM is stopped
        self.assertTrue(test_vm_object.getState() is PowerStates.STOPPED)

    def test_stop_stopped_vm(self):
        """Attempts to stop an already stopped VM"""
        # Create Virtual machine
        VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks']
        )

        # Use argument parser to start the VM
        with self.assertRaises(VmAlreadyStoppedException):
            self.parser.parse_arguments(
                'stop %s' %
                self.test_vms['TEST_VM_1']['name'],
                mcvirt_instance=self.mcvirt)

    @unittest.skipIf(not NodeDRBD.isEnabled(),
                     'DRBD is not enabled on this node')
    def test_offline_migrate(self):
        from mcvirt.virtual_machine.hard_drive.drbd import DrbdDiskState
        from mcvirt.cluster.cluster import Cluster
        import time
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='DRBD')

        # Get the first available remote node for the VM
        node_name = test_vm_object._getRemoteNodes()[0]

        # Assert that the VM is registered locally
        self.assertTrue(test_vm_object.isRegisteredLocally())

        # Monitor the hard drives until they are synced
        for disk_object in test_vm_object.getDiskObjects():
            while (
                disk_object._drbdGetDiskState() != (
                    DrbdDiskState.UP_TO_DATE,
                    DrbdDiskState.UP_TO_DATE)):
                time.sleep(5)

        # Migrate VM to remote node
        try:
            self.parser.parse_arguments(
                'migrate --node %s %s' %
                (node_name,
                 test_vm_object.getName()),
                mcvirt_instance=self.mcvirt)
        except DrbdStateException:
            # If the migration fails, attempt to manually register locally before failing
            test_vm_object.register()
            raise

        # Ensure the VM node matches the destination node
        self.assertEqual(test_vm_object.getNode(), node_name)

        cluster_instance = Cluster(self.mcvirt)
        remote_node = cluster_instance.getRemoteNode(node_name)

        # Attempt to start the VM on the remote node
        remote_node.runRemoteCommand('virtual_machine-start',
                                     {'vm_name': test_vm_object.getName()})

        # Ensure VM is running
        self.assertTrue(test_vm_object.getState() is PowerStates.RUNNING)

        # Attempt to stop the VM on the remote node
        remote_node.runRemoteCommand('virtual_machine-stop',
                                     {'vm_name': test_vm_object.getName()})

        # Ensure VM is stopped
        self.assertTrue(test_vm_object.getState() is PowerStates.STOPPED)

        # Manually unregister VM from remote node
        remote_node.runRemoteCommand('virtual_machine-unregister',
                                     {'vm_name': test_vm_object.getName()})
        test_vm_object._setNode(None)

        # Manually register VM on local node
        test_vm_object.register()

        # Delete VM
        test_vm_object.delete(True)

        # Ensure VM no longer exists
        self.assertFalse(
            VirtualMachine._checkExists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vms['TEST_VM_1']['name']))

    def test_lock(self):
        """Exercise VM locking"""
        from mcvirt.virtual_machine.virtual_machine import LockStates
        # Create a test VM
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vms['TEST_VM_1']['name'],
            self.test_vms['TEST_VM_1']['cpu_count'],
            self.test_vms['TEST_VM_1']['memory_allocation'],
            self.test_vms['TEST_VM_1']['disk_size'],
            self.test_vms['TEST_VM_1']['networks'],
            storage_type='Local')

        # Ensure the VM is initially unlocked
        self.assertEqual(test_vm_object.getLockState(), LockStates.UNLOCKED)

        # Lock the VM, using the argument parser
        self.parser.parse_arguments(
            'lock --lock %s' %
            test_vm_object.getName(),
            mcvirt_instance=self.mcvirt)

        # Ensure the VM is reported as locked
        self.assertEqual(test_vm_object.getLockState(), LockStates.LOCKED)

        # Attempt to start the VM
        with self.assertRaises(VirtualMachineLockException):
            test_vm_object.start()

        # Attempt to unlock using the argument parser
        self.parser.parse_arguments(
            'lock --unlock %s' %
            test_vm_object.getName(),
            mcvirt_instance=self.mcvirt)

        # Ensure the VM can be started
        test_vm_object.start()
        test_vm_object.stop()

        # Attempt to unlock the VM again, ensuring an exception is thrown
        with self.assertRaises(VirtualMachineLockException):
            self.parser.parse_arguments(
                'lock --unlock %s' %
                test_vm_object.getName(),
                mcvirt_instance=self.mcvirt)

    @unittest.skipIf(NodeDRBD.isEnabled(),
                     'DRBD is enabled on this node')
    def test_unspecified_storage_type_local(self):
        """Create a VM without specifying the storage type"""
        # Create virtual machine using parser, without specifying the storage_type
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_1']['cpu_count'],
                                     self.test_vms['TEST_VM_1']['disk_size'][0],
                                     self.test_vms['TEST_VM_1']['memory_allocation']) +
                                    ' --network %s' % self.test_vms['TEST_VM_1']['networks'][0],
                                    mcvirt_instance=self.mcvirt)

        # Ensure that the VM exists
        self.assertTrue(
            VirtualMachine._checkExists(self.mcvirt.getLibvirtConnection(),
                                        self.test_vms['TEST_VM_1']['name']))

    @unittest.skipIf(not NodeDRBD.isEnabled(),
                     'DRBD is not enabled on this node')
    def test_unspecified_storage_type_drbd(self):
        """Create a VM without specifying the storage type"""
        # Create virtual machine using parser, without specifying the storage_type.
        # Assert that an exception is thrown as the storage_type has not been specified
        with self.assertRaises(MCVirtException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s' %
                                        self.test_vms['TEST_VM_1']['networks'][0],
                                        mcvirt_instance=self.mcvirt)

    def test_invalid_network_name(self):
        """Attempts to create a VM using a network that does not exist"""
        with self.assertRaises(NetworkDoesNotExistException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network non-existent-network' +
                                        ' --storage-type Local',
                                        mcvirt_instance=self.mcvirt)

    def test_create_alternative_driver(self):
        """Creates VMs using alternative hard drive drivers"""
        for disk_driver in [['IDE', 'ide'], ['VIRTIO', 'virtio'], ['SCSI', 'scsi']]:
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0],
                                         'Local') +
                                        ' --driver %s' % disk_driver[0],
                                        mcvirt_instance=self.mcvirt)

            vm_object = VirtualMachine(self.mcvirt, self.test_vms['TEST_VM_1']['name'])
            domain_xml_string = vm_object._getLibvirtDomainObject().XMLDesc()
            domain_config = ET.fromstring(domain_xml_string)
            self.assertEqual(find('./devices/disk[@type="block"]/target').get('bus'),
                             disk_driver[1])
            vm_object.delete(True)

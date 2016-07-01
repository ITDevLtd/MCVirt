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
import tempfile
import time

from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.constants import PowerStates, LockStates, DirectoryLocation
from mcvirt.exceptions import (InvalidVirtualMachineNameException,
                               VmAlreadyExistsException,
                               VmDirectoryAlreadyExistsException,
                               VmAlreadyStartedException,
                               VmAlreadyStoppedException,
                               CannotStartClonedVmException,
                               CannotDeleteClonedVmException,
                               CannotCloneDrbdBasedVmsException,
                               VirtualMachineLockException,
                               NetworkDoesNotExistException,
                               DrbdStateException,
                               DrbdNotEnabledOnNode,
                               UnknownStorageTypeException)
from mcvirt.test.test_base import TestBase, skip_drbd
from mcvirt.virtual_machine.hard_drive.drbd import DrbdDiskState


class VirtualMachineTests(TestBase):
    """Provide unit tests for the VirtualMachine class"""

    @staticmethod
    def suite():
        """Return a test suite of the Virtual Machine tests"""
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
        suite.addTest(VirtualMachineTests('test_live_iso_change'))

        # # Add tests for Drbd
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

    def test_create_local(self):
        """Perform the test_create test with Local storage"""
        self.test_create('Local')

    @skip_drbd(True)
    def test_create_drbd(self):
        """Perform the test_create test with Drbd storage"""
        self.test_create('Drbd')

    def test_create(self, storage_type):
        """Test the creation of VMs through the argument parser"""
        # Ensure VM does not exist
        self.assertFalse(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Create virtual machine using parser
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_1']['cpu_count'],
                                     self.test_vms['TEST_VM_1']['disk_size'][0],
                                     self.test_vms['TEST_VM_1']['memory_allocation']) +
                                    ' --network %s --storage-type %s' %
                                    (self.test_vms['TEST_VM_1']['networks'][0],
                                     storage_type))

        # Ensure VM exists
        self.assertTrue(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Obtain VM object
        vm_object = self.vm_factory.getVirtualMachineByName(self.test_vms['TEST_VM_1']['name'])
        self.rpc.annotate_object(vm_object)

        # Check each of the attributes for VM
        self.assertEqual(int(vm_object.getRAM()),
                         self.test_vms['TEST_VM_1']['memory_allocation'] * 1024)
        self.assertEqual(vm_object.getCPU(), str(self.test_vms['TEST_VM_1']['cpu_count']))

        # Ensure second VM does not exist
        self.assertFalse(self.vm_factory.check_exists(self.test_vms['TEST_VM_2']['name']))

        # Create second VM
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_2']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_2']['cpu_count'],
                                     self.test_vms['TEST_VM_2']['disk_size'][0],
                                     self.test_vms['TEST_VM_2']['memory_allocation']) +
                                    ' --network %s --storage-type %s' %
                                    (self.test_vms['TEST_VM_2']['networks'][0],
                                     storage_type))

        # Ensure VM exists
        self.assertTrue(self.vm_factory.check_exists(self.test_vms['TEST_VM_2']['name']))

        # Obtain VM object
        vm_object_2 = self.vm_factory.getVirtualMachineByName(self.test_vms['TEST_VM_2']['name'])
        self.rpc.annotate_object(vm_object_2)
        vm_object_2.delete(True)

    @skip_drbd(False)
    def test_create_drbd_not_enabled(self):
        """Attempt to create a VM with Drbd storage on a node that doesn't have Drbd enabled"""
        # Attempt to create VM and ensure exception is thrown
        with self.assertRaises(DrbdNotEnabledOnNode):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0], 'Drbd'))

    def test_delete_local(self):
        """Perform the test_delete test with Local storage"""
        self.test_delete('Local')

    @skip_drbd(True)
    def test_delete_drbd(self):
        """Perform the test_delete test with Drbd storage"""
        self.test_delete('Drbd')

    def test_delete(self, storage_type):
        """Test the deletion of a VM through the argument parser"""
        # Create Virtual machine
        self.create_vm('TEST_VM_1', storage_type)

        # Remove VM using parser
        self.parser.parse_arguments('delete %s --remove-data' % self.test_vms['TEST_VM_1']['name'])

        # Ensure VM has been deleted
        self.assertFalse(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Ensure that VM directory does not exist
        self.assertFalse(os.path.exists(
            VirtualMachine._get_vm_dir(self.test_vms['TEST_VM_1']['name'])
        ))

    def test_clone_local(self):
        """Test the VM cloning in MCVirt using the argument parser"""
        # Create Virtual machine
        test_vm_parent = self.create_vm('TEST_VM_1', 'Local')

        test_data = os.urandom(8)

        # Obtain the disk path for the VM and write random data to it
        for disk_object in test_vm_parent.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            fh = open(disk_object.getDiskPath(), 'w')
            fh.write(test_data)
            fh.close()

        # Clone VM
        self.parser.parse_arguments(
            'clone --template %s %s' %
            (self.test_vms['TEST_VM_1']['name'],
             self.test_vms['TEST_VM_2']['name']))

        test_vm_clone = self.vm_factory.getVirtualMachineByName(
            self.test_vms['TEST_VM_2']['name']
        )
        self.rpc.annotate_object(test_vm_clone)

        # Check data is present on target VM
        for disk_object in test_vm_clone.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            fh = open(disk_object.getDiskPath(), 'r')
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

    @skip_drbd(True)
    def test_clone_drbd(self):
        """Attempt to clone a Drbd-based VM"""
        # Create parent VM
        test_vm_parent = self.create_vm('TEST_VM_1', 'Drbd')

        # Attempt to clone VM
        with self.assertRaises(CannotCloneDrbdBasedVmsException):
            self.parser.parse_arguments(
                'clone --template %s %s' %
                (self.test_vms['TEST_VM_1']['name'],
                 self.test_vms['TEST_VM_2']['name']))

        test_vm_parent.delete(True)

    def test_duplicate_local(self):
        """Perform test_duplicate test with Local storage"""
        self.test_duplicate('Local')

    @skip_drbd(True)
    def test_duplicate_drbd(self):
        """Perform the test_duplicate test with Drbd storage"""
        self.test_duplicate('Drbd')

    def test_duplicate(self, storage_type):
        """Attempt to duplicate a VM using the argument parser and perform tests
        on the parent and duplicate VM
        """
        # Create Virtual machine
        test_vm_parent = self.create_vm('TEST_VM_1', 'Local')

        test_data = os.urandom(8)

        # Obtain the disk path for the VM and write random data to it
        for disk_object in test_vm_parent.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            fh = open(disk_object.getDiskPath(), 'w')
            fh.write(test_data)
            fh.close()

        # Clone VM
        self.parser.parse_arguments(
            'duplicate --template %s %s' %
            (self.test_vms['TEST_VM_1']['name'],
             self.test_vms['TEST_VM_2']['name']))
        test_vm_duplicate = self.vm_factory.getVirtualMachineByName(
            self.test_vms['TEST_VM_2']['name']
        )
        self.rpc.annotate_object(test_vm_duplicate)

        # Check data is present on target VM
        for disk_object in test_vm_duplicate.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            fh = open(disk_object.getDiskPath(), 'r')
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
        """Attempt to create a virtual machine with an invalid name"""
        invalid_vm_name = 'invalid.name+'

        # Ensure VM does not exist
        self.assertFalse(self.vm_factory.check_exists(invalid_vm_name))

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
                 'Local'))

        # Ensure VM has not been created
        self.assertFalse(self.vm_factory.check_exists(invalid_vm_name))

    def test_create_duplicate(self):
        """Attempt to create two VMs with the same name"""
        # Create Virtual machine
        original_memory_allocation = 200
        test_vm_object = self.vm_factory.create(
            self.test_vms['TEST_VM_1']['name'],
            1,
            original_memory_allocation,
            [100],
            ['Production'],
            storage_type='Local')
        self.rpc.annotate_object(test_vm_object)
        self.assertTrue(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Attempt to create VM with duplicate name, ensuring that an exception is thrown
        with self.assertRaises(VmAlreadyExistsException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0],
                                         'Local'))

        # Ensure original VM already exists
        self.assertTrue(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Check memory amount of VM matches original VM
        self.assertEqual(int(test_vm_object.getRAM()), int(original_memory_allocation))

        # Remove test VM
        test_vm_object.delete(True)

    def test_vm_directory_already_exists(self):
        """Attempt to create a VM whilst the directory for the VM already exists"""
        # Create the directory for the VM
        os.makedirs(VirtualMachine._get_vm_dir(self.test_vms['TEST_VM_1']['name']))

        # Attempt to create VM, expecting an exception for the directory already existing
        with self.assertRaises(VmDirectoryAlreadyExistsException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0],
                                         'Local'))

        # Ensure the VM has not been created
        self.assertFalse(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

        # Remove directory
        shutil.rmtree(VirtualMachine._get_vm_dir(self.test_vms['TEST_VM_1']['name']))

    def test_start_local(self):
        """Perform the test_start test with Local storage"""
        self.test_start('Local')

    @skip_drbd(True)
    def test_start_drbd(self):
        """Perform the test_start test with Drbd storage"""
        self.test_start('DRDB')

    def test_start(self, storage_type):
        """Test starting VMs through the argument parser"""
        # Create Virtual machine
        test_vm_object = self.create_vm('TEST_VM_1', storage_type)

        # Use argument parser to start the VM
        self.parser.parse_arguments('start %s' % self.test_vms['TEST_VM_1']['name'])

        # Ensure that it is running
        self.assertTrue(test_vm_object.getPowerState() is PowerStates.RUNNING.value)

    def test_start_running_vm(self):
        """Attempt to start a running VM"""
        # Create Virtual machine and start it
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')
        test_vm_object.start()

        # Use argument parser to start the VM
        with self.assertRaises(VmAlreadyStartedException):
            self.parser.parse_arguments(
                'start %s' %
                self.test_vms['TEST_VM_1']['name'])

    def test_reset(self):
        """Reset a running VM"""
        # Create Virtual machine and start it
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')
        test_vm_object.start()

        # Use argument parser to reset the VM
        self.parser.parse_arguments(
            'reset %s' %
            self.test_vms['TEST_VM_1']['name'])

    def test_reset_stopped_vm(self):
        """Attempt to reset a stopped VM"""
        # Create Virtual machine and start it
        self.create_vm('TEST_VM_1', 'Local')

        # Use argument parser to reset the VM
        with self.assertRaises(VmAlreadyStoppedException):
            self.parser.parse_arguments(
                'reset %s' %
                self.test_vms['TEST_VM_1']['name'])

    def test_stop_local(self):
        """Perform the test_stop test with Local storage"""
        self.test_stop('Local')

    @skip_drbd(True)
    def test_stop_drbd(self):
        """Perform the test_stop test with Drbd storage"""
        self.test_stop('Drbd')

    def test_stop(self, storage_type):
        """Test stopping VMs through the argument parser"""
        # Create virtual machine for testing
        test_vm_object = self.create_vm('TEST_VM_1', storage_type)

        # Start VM and ensure it is running
        test_vm_object.start()
        self.assertTrue(test_vm_object.getPowerState() is PowerStates.RUNNING.value)

        # Use the argument parser to stop the VM
        self.parser.parse_arguments(
            'stop %s' %
            self.test_vms['TEST_VM_1']['name'])

        # Ensure the VM is stopped
        self.assertTrue(test_vm_object.getPowerState() is PowerStates.STOPPED.value)

    def test_stop_stopped_vm(self):
        """Attempt to stop an already stopped VM"""
        # Create Virtual machine
        self.create_vm('TEST_VM_1', 'Local')

        # Use argument parser to start the VM
        with self.assertRaises(VmAlreadyStoppedException):
            self.parser.parse_arguments(
                'stop %s' %
                self.test_vms['TEST_VM_1']['name'])

    @skip_drbd(True)
    def test_offline_migrate(self):
        """Test the offline migration of a VM"""
        test_vm_object = self.create_vm('TEST_VM_1', 'Drbd')

        # Get the first available remote node for the VM
        node_name = test_vm_object.get_remote_nodes()[0]

        # Assert that the VM is registered locally
        self.assertTrue(test_vm_object.isRegisteredLocally())

        # Monitor the hard drives until they are synced
        for disk_object in test_vm_object.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            while (
                disk_object.drbdGetDiskState() != (
                    DrbdDiskState.UP_TO_DATE.value,
                    DrbdDiskState.UP_TO_DATE.value)):
                time.sleep(5)

        # Migrate VM to remote node
        try:
            self.parser.parse_arguments(
                'migrate --node %s %s' %
                (node_name,
                 test_vm_object.get_name()))
        except DrbdStateException:
            # If the migration fails, attempt to manually register locally before failing
            test_vm_object.register()
            raise

        # Ensure the VM node matches the destination node
        self.assertEqual(test_vm_object.getNode(), node_name)

        # Attempt to start the VM on the remote node
        self.parser.parse_arguments('start %s' % self.test_vms['TEST_VM_1']['name'])

        # Ensure VM is running
        self.assertTrue(test_vm_object.getPowerState() is PowerStates.RUNNING.value)

        # Attempt to stop the VM on the remote node
        self.parser.parse_arguments('stop %s' % self.test_vms['TEST_VM_1']['name'])

        # Ensure VM is stopped
        self.assertTrue(test_vm_object.getPowerState() is PowerStates.STOPPED.value)

        # Delete VM
        test_vm_object.delete(True)

        # Ensure VM no longer exists
        self.assertFalse(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

    def test_lock(self):
        """Exercise VM locking"""
        # Create a test VM
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        # Ensure the VM is initially unlocked
        self.assertEqual(test_vm_object.getLockState(), LockStates.UNLOCKED.value)

        # Lock the VM, using the argument parser
        self.parser.parse_arguments('lock --lock %s' % test_vm_object.get_name())

        # Ensure the VM is reported as locked
        self.assertEqual(test_vm_object.getLockState(), LockStates.LOCKED.value)

        # Attempt to start the VM
        with self.assertRaises(VirtualMachineLockException):
            test_vm_object.start()

        # Attempt to unlock using the argument parser
        self.parser.parse_arguments('lock --unlock %s' % test_vm_object.get_name())

        # Ensure the VM can be started
        test_vm_object.start()
        test_vm_object.stop()

        # Attempt to unlock the VM again, ensuring an exception is thrown
        with self.assertRaises(VirtualMachineLockException):
            self.parser.parse_arguments('lock --unlock %s' % test_vm_object.get_name())

    @skip_drbd(False)
    def test_unspecified_storage_type_local(self):
        """Create a VM without specifying the storage type"""
        # Create virtual machine using parser, without specifying the storage_type
        self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                    ' --cpu-count %s --disk-size %s --memory %s' %
                                    (self.test_vms['TEST_VM_1']['cpu_count'],
                                     self.test_vms['TEST_VM_1']['disk_size'][0],
                                     self.test_vms['TEST_VM_1']['memory_allocation']) +
                                    ' --network %s' % self.test_vms['TEST_VM_1']['networks'][0])

        # Ensure that the VM exists
        self.assertTrue(self.vm_factory.check_exists(self.test_vms['TEST_VM_1']['name']))

    @skip_drbd(True)
    def test_unspecified_storage_type_drbd(self):
        """Create a VM without specifying the storage type"""
        # Create virtual machine using parser, without specifying the storage_type.
        # Assert that an exception is thrown as the storage_type has not been specified
        with self.assertRaises(UnknownStorageTypeException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s' %
                                        self.test_vms['TEST_VM_1']['networks'][0])

    def test_invalid_network_name(self):
        """Attempt to create a VM using a network that does not exist"""
        with self.assertRaises(NetworkDoesNotExistException):
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network nonexistentnetwork' +
                                        ' --storage-type Local')

    def test_create_alternative_driver(self):
        """Create VMs using alternative hard drive drivers"""
        for disk_driver in [['IDE', 'ide'], ['VIRTIO', 'virtio'], ['SCSI', 'scsi']]:
            self.parser.parse_arguments('create %s' % self.test_vms['TEST_VM_1']['name'] +
                                        ' --cpu-count %s --disk-size %s --memory %s' %
                                        (self.test_vms['TEST_VM_1']['cpu_count'],
                                         self.test_vms['TEST_VM_1']['disk_size'][0],
                                         self.test_vms['TEST_VM_1']['memory_allocation']) +
                                        ' --network %s --storage-type %s' %
                                        (self.test_vms['TEST_VM_1']['networks'][0],
                                         'Local') +
                                        ' --driver %s' % disk_driver[0])

            vm_object = self.vm_factory.getVirtualMachineByName(self.test_vms['TEST_VM_1']['name'])
            self.rpc.annotate_object(vm_object)
            domain_xml_string = vm_object.get_libvirt_xml()
            domain_config = ET.fromstring(domain_xml_string)
            self.assertEqual(
                domain_config.find('./devices/disk[@type="block"]/target').get('bus'),
                disk_driver[1]
            )
            vm_object.delete(True)

    def test_live_iso_change(self):
        """Change the ISO attached to a running VM"""
        # Create a test VM and start
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')
        test_vm_object.start()

        # Create temp file, for use as fake ISO
        temp_file = tempfile.NamedTemporaryFile(dir=DirectoryLocation.ISO_STORAGE_DIR,
                                                suffix='.iso')
        iso_name = temp_file.name.split('/')[-1]
        iso_path = temp_file.name
        temp_file.close()

        fhandle = open(iso_path, 'a')
        try:
            fhandle.write('test')
            os.utime(iso_path, None)
        finally:
            fhandle.close()

        self.parser.parse_arguments('update %s --attach-iso %s' %
                                    (self.test_vms['TEST_VM_1']['name'],
                                     iso_name))

        domain_xml_string = test_vm_object.get_libvirt_xml()
        domain_config = ET.fromstring(domain_xml_string)
        self.assertEqual(
            domain_config.find('./devices/disk[@device="cdrom"]/source').get('file'),
            iso_path
        )

        test_vm_object.stop()
        test_vm_object.delete(True)

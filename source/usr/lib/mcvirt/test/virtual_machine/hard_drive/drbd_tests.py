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
import time

from mcvirt.test.common import stop_and_delete
from mcvirt.node.drbd import Drbd as NodeDrbd
from mcvirt.virtual_machine.hard_drive.drbd import DrbdConnectionState, DrbdVolumeNotInSyncException
from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.parser import Parser
from mcvirt.mcvirt import MCVirt
from mcvirt.system import System


class DrbdTests(unittest.TestCase):
    """Provides unit tests for the Drbd hard drive class"""

    @staticmethod
    def suite():
        """Returns a test suite of the Virtual Machine tests"""
        suite = unittest.TestSuite()
        suite.addTest(DrbdTests('test_verify'))

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
                }
            }

        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vms['TEST_VM_1']['name'])
        self.mcvirt = None

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_verify(self):
        """Test the Drbd verification for both in-sync and out-of-sync Drbd volumes"""
        # Create Virtual machine
        test_vm_object = VirtualMachine.create(self.mcvirt, self.test_vms['TEST_VM_1']['name'],
                                               self.test_vms['TEST_VM_1']['cpu_count'],
                                               self.test_vms['TEST_VM_1']['memory_allocation'],
                                               self.test_vms['TEST_VM_1']['disk_size'],
                                               self.test_vms['TEST_VM_1']['networks'],
                                               storage_type='Drbd')
        self.assertTrue(VirtualMachine._check_exists(self.mcvirt.getLibvirtConnection(),
                                                    self.test_vms['TEST_VM_1']['name']))

        # Wait for 10 seconds after creation to ensure that Drbd
        # goes into connection -> Resyncing state
        time.sleep(10)

        # Wait until the Drbd resource is synced
        for disk_object in test_vm_object.getHardDriveObjects():
            wait_timeout = 6
            while (disk_object._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
                # If the Drbd volume has not connected within 1 minute, throw an exception
                if (not wait_timeout):
                    raise DrbdVolumeNotInSyncException('Wait for Drbd connection timed out')

                time.sleep(10)
                wait_timeout -= 1

        # Perform verification on VM, using the argument parser
        self.parser.parse_arguments('verify %s' % self.test_vms['TEST_VM_1']['name'],
                                    mcvirt_instance=self.mcvirt)

        # Ensure the disks are in-sync
        for disk_object in test_vm_object.getHardDriveObjects():
            self.assertTrue(disk_object._isInSync())

        # Obtain the Drbd raw volume for the VM and write random data to it
        for disk_object in test_vm_object.getHardDriveObjects():
            config_object = disk_object.get_config_object()
            drbd_raw_suffix = config_object.Drbd_RAW_SUFFIX
            raw_logical_volume_name = config_object._getLogicalVolumeName(drbd_raw_suffix)
            raw_logical_volume_path = config_object._getLogicalVolumePath(raw_logical_volume_name)
            System.runCommand(['dd', 'if=/dev/urandom',
                               'of=%s' % raw_logical_volume_path,
                               'bs=1M', 'count=8'])
            System.runCommand(['sync'])

        # Perform another verification and ensure that an exception is raised
        with self.assertRaises(DrbdVolumeNotInSyncException):
            self.parser.parse_arguments('verify %s' % self.test_vms['TEST_VM_1']['name'],
                                        mcvirt_instance=self.mcvirt)

        # Attempt to start the VM, ensuring an exception is raised
        with self.assertRaises(DrbdVolumeNotInSyncException):
            test_vm_object.start()

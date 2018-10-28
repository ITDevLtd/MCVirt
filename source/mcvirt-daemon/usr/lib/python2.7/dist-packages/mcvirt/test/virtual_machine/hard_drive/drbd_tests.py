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
import time

from mcvirt.virtual_machine.hard_drive.drbd import DrbdConnectionState
from mcvirt.exceptions import DrbdVolumeNotInSyncException
from mcvirt.system import System
from mcvirt.test.test_base import TestBase, skip_drbd


class DrbdTests(TestBase):
    """Provides unit tests for the Drbd hard drive class"""

    @staticmethod
    def suite():
        """Return a test suite of the Virtual Machine tests"""
        suite = unittest.TestSuite()
        suite.addTest(DrbdTests('test_verify'))

        return suite

    @skip_drbd(True)
    def test_verify(self):
        """Test the Drbd verification for both in-sync and out-of-sync Drbd volumes"""
        # Create Virtual machine
        test_vm_object = self.create_vm('TEST_VM_1', 'Drbd')
        self.assertTrue(self.vm_factory.check_exists_by_name(self.test_vms['TEST_VM_1']['name']))

        # Wait for 10 seconds after creation to ensure that Drbd
        # goes into connection -> Resyncing state
        time.sleep(10)

        # Wait until the Drbd resource is synced
        for disk_object in test_vm_object.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            wait_timeout = 6
            while disk_object.drbdGetConnectionState()[1] != DrbdConnectionState.CONNECTED.value:
                # If the Drbd volume has not connected within 1 minute, throw an exception
                if not wait_timeout:
                    raise DrbdVolumeNotInSyncException('Wait for Drbd connection timed out')

                time.sleep(10)
                wait_timeout -= 1

        # Perform verification on VM, using the argument parser
        self.parser.parse_arguments('verify %s' % self.test_vms['TEST_VM_1']['name'])

        # Ensure the disks are in-sync
        for disk_object in test_vm_object.getHardDriveObjects():
            self.rpc_annotate_object(disk_object)
            self.assertTrue(disk_object._isInSync())

        # Obtain the Drbd raw volume for the VM and write random data to it
        for disk_object in test_vm_object.getHardDriveObjects():
            self.rpc.annotate_object(disk_object)
            drbd_raw_suffix = disk_object.DRBD_RAW_SUFFIX
            raw_logical_volume_name = disk_object._getLogicalVolumeName(drbd_raw_suffix)
            raw_logical_volume_path = disk_object._getLogicalVolumePath(raw_logical_volume_name)
            System.runCommand(['dd', 'if=/dev/urandom',
                               'of=%s' % raw_logical_volume_path,
                               'bs=1M', 'count=8'])
            System.runCommand(['sync'])

        # Perform another verification and ensure that an exception is raised
        with self.assertRaises(DrbdVolumeNotInSyncException):
            self.parser.parse_arguments('verify %s' % self.test_vms['TEST_VM_1']['name'])

        # Attempt to start the VM, ensuring an exception is raised
        with self.assertRaises(DrbdVolumeNotInSyncException):
            test_vm_object.start()

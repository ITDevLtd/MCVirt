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

import Pyro4
import libvirt
import os

from mcvirt.system import System
from mcvirt.exceptions import (VmAlreadyStartedException, VmIsCloneException,
                               ExternalStorageCommandErrorException,
                               DiskAlreadyExistsException,
                               CannotMigrateLocalDiskException,
                               MCVirtCommandException)
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.auth import Auth
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.lock import locking_method


class Local(Base):
    """Provides operations to manage local hard drives, used by VMs"""

    MAXIMUM_DEVICES = 4
    CACHE_MODE = 'directsync'

    def __init__(self, *args, **kwargs):
        """Sets member variables and obtains libvirt domain object"""
        super(Local, self).__init__(*args, **kwargs)

    @staticmethod
    def isAvailable(pyro_object):
        """Determine if local storage is available on the node"""
        return pyro_object._get_registered_object('node').is_volume_group_set()

    @Pyro4.expose()
    @locking_method()
    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self.vm_object
        )

        # Ensure disk exists
        self._ensure_exists()

        # Ensure VM is stopped
        from mcvirt.virtual_machine.virtual_machine import PowerStates
        if (self.vm_object._getPowerState() is not PowerStates.STOPPED):
            raise VmAlreadyStartedException('VM must be stopped before increasing disk size')

        # Ensure that VM has not been cloned and is not a clone
        if (self.vm_object.getCloneParent() or self.vm_object.getCloneChildren()):
            raise VmIsCloneException('Cannot increase the disk of a cloned VM or a clone.')

        command_args = ('lvextend', '-L', '+%sM' % increase_size,
                        self._getDiskPath())
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst extending logical volume:\n" + str(e)
            )

    def _check_exists(self):
        """Checks if a disk exists, which is required before any operations
        can be performed on the disk"""
        self._ensureLogicalVolumeExists(
            self._getDiskName())
        return True

    def _removeStorage(self):
        """Removes the backing logical volume"""
        self._ensure_exists()
        self._removeLogicalVolume(self._getDiskName())

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensure_exists()
        return self._get_logical_volume_size(self._getDiskName())

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        self._ensure_exists()
        new_disk = Local(vm_object=destination_vm_object, driver=self.driver,
                         disk_id=self.disk_id)
        self._register_object(new_disk)
        new_logical_volume_name = new_disk._getDiskName()
        disk_size = self.getSize()

        # Perform a logical volume snapshot
        command_args = ('lvcreate', '-L', '%sM' % disk_size, '-s',
                        '-n', new_logical_volume_name, self._getDiskPath())
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst cloning disk logical volume:\n" + str(e)
            )

        new_disk.addToVirtualMachine()
        return new_disk

    def create(self, size):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        disk_path = self._getDiskPath()
        logical_volume_name = self._getDiskName()

        # Ensure the disk doesn't already exist
        if (os.path.lexists(disk_path)):
            raise DiskAlreadyExistsException('Disk already exists: %s' % disk_path)

        # Create the raw disk image
        self._createLogicalVolume(logical_volume_name, size)

        # Attach to VM and create disk object
        self.addToVirtualMachine()

    def activateDisk(self):
        """Starts the disk logical volume"""
        self._ensure_exists()
        self._activateLogicalVolume(self._getDiskName())

    def deactivateDisk(self):
        """Deactivates the disk loglcal volume"""
        self._ensure_exists()

    def preMigrationChecks(self):
        """Perform pre-migration checks"""
        raise CannotMigrateLocalDiskException('VMs using local disks cannot be migrated')

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        return self._getLogicalVolumePath(self._getDiskName())

    def _getDiskName(self):
        """Returns the name of a disk logical volume, for a given VM"""
        vm_name = self.vm_object.get_name()
        return 'mcvirt_vm-%s-disk-%s' % (vm_name, self.disk_id)

    def _getMCVirtConfig(self):
        """Returns the MCVirt hard drive configuration for the Local hard drive"""
        # There are no configurations for the disk stored by MCVirt
        return super(Local, self)._getMCVirtConfig()

    def _getBackupLogicalVolume(self):
        """Returns the storage device for the backup"""
        return self._getDiskName()

    def _getBackupSnapshotLogicalVolume(self):
        """Returns the logical volume name for the backup snapshot"""
        return self._getDiskName + self.SNAPSHOT_SUFFIX

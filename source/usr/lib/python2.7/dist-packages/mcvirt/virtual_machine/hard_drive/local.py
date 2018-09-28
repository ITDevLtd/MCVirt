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

import os

from mcvirt.system import System
from mcvirt.exceptions import (VmAlreadyStartedException, VmIsCloneException,
                               ExternalStorageCommandErrorException,
                               DiskAlreadyExistsException,
                               CannotMigrateLocalDiskException,
                               MCVirtCommandException)
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.expose_method import Expose


class Local(Base):
    """Provides operations to manage local hard drives, used by VMs"""

    MAXIMUM_DEVICES = 4
    CACHE_MODE = 'directsync'

    def __init__(self, custom_disk_name=None, *args, **kwargs):
        """Set member variables and obtains libvirt domain object"""
        self._custom_disk_name = custom_disk_name
        super(Local, self).__init__(*args, **kwargs)

    @property
    def disk_name(self):
        """Return disk name"""
        if self.custom_disk_name:
            return self.custom_disk_name
        vm_name = self.vm_object.get_name()
        return 'mcvirt_vm-%s-disk-%s' % (vm_name, self.disk_id)

    @property
    def custom_disk_name(self):
        """Return custom disk name"""
        return self._custom_disk_name

    @property
    def config_properties(self):
        """Return the disk object config items"""
        return super(Local, self).config_properties + ['custom_disk_name']

    @staticmethod
    def isAvailable(storage_factory, node_drdb):
        """Determine if local storage is available on the node"""
        return bool(storage_factory.get_all(available_on_local_node=True))

    def _get_data_volume(self):
        """Obtain the data volume object for the disk"""
        return self._get_volume(self.disk_name)

    @Expose(locking=True)
    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self.vm_object
        )

        # Ensure disk exists
        self._ensure_exists()

        # Ensure VM is stopped
        if not self.vm_object.is_stopped:
            raise VmAlreadyStartedException('VM must be stopped before increasing disk size')

        # Ensure that VM has not been cloned and is not a clone
        if self.vm_object.getCloneParent() or self.vm_object.getCloneChildren():
            raise VmIsCloneException('Cannot increase the disk of a cloned VM or a clone.')

        # Obtain volume for the disk and resize
        volume = self._get_data_volume()
        volume.resize(increase_size, increase=True)

    def _check_exists(self):
        """Checks if a disk exists, which is required before any operations
        can be performed on the disk"""
        return self._get_data_volume().check_exists()

    def _removeStorage(self):
        """Removes the backing logical volume"""
        self._get_data_volume().delete()

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        return self._get_data_volume().get_size()

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        self._ensure_exists()
        new_disk = Local(vm_object=destination_vm_object, driver=self.driver,
                         disk_id=self.disk_id)
        self._register_object(new_disk)

        # Clone original volume to new volume
        self._get_data_volume().clone(new_disk._get_data_volume())

        new_disk.addToVirtualMachine()
        return new_disk

    def create(self, size):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        self._get_data_volume().create(size)

        # Attach to VM and create disk object
        self.addToVirtualMachine()

    def activateDisk(self):
        """Starts the disk logical volume"""
        self._ensure_exists()
        self._get_data_volume().activate()

    def deactivateDisk(self):
        """Deactivates the disk loglcal volume"""
        self._get_data_volume().deactivate()

    def preMigrationChecks(self):
        """Perform pre-migration checks"""
        # @TODO Allow migration for shared disks - worth ensuring that the disks is actually
        # available on both nodes
        if not self.get_storage_backend().shared:
            raise CannotMigrateLocalDiskException('VMs using local disks cannot be migrated')

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        return self._get_data_volume().get_path()

    def _getDiskName(self):
        """Returns the name of a disk logical volume, for a given VM"""
        return self.disk_name

    def _getMCVirtConfig(self):
        """Returns the MCVirt hard drive configuration for the Local hard drive"""
        # There are no configurations for the disk stored by MCVirt
        return super(Local, self)._getMCVirtConfig()

    def _getBackupLogicalVolume(self):
        """Returns the storage device for the backup"""
        return self._getDiskName()

    def _getBackupSnapshotLogicalVolume(self):
        """Returns the logical volume name for the backup snapshot"""
        return self._getDiskName() + self.SNAPSHOT_SUFFIX

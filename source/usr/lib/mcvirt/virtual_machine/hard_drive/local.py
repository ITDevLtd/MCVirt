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

import libvirt
import os

from mcvirt.system import System, MCVirtCommandException
from mcvirt.mcvirt import MCVirtException
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.local import Local as ConfigLocal


class CannotMigrateLocalDiskException(MCVirtException):
    """Local disks cannot be migrated"""
    pass


class Local(Base):
    """Provides operations to manage local hard drives, used by VMs"""

    def __init__(self, vm_object, disk_id):
        """Sets member variables and obtains libvirt domain object"""
        self.config = ConfigLocal(vm_object=vm_object, disk_id=disk_id, registered=True)
        super(Local, self).__init__(disk_id=disk_id)

    @staticmethod
    def isAvailable():
        """Determine if local storage is available on the node"""
        return True

    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        self._ensureExists()
        # Ensure VM is stopped
        from mcvirt.virtual_machine.virtual_machine import PowerStates
        if (self.getVmObject().getState() is not PowerStates.STOPPED):
            raise MCVirtException('VM must be stopped before increasing disk size')

        # Ensure that VM has not been cloned and is not a clone
        if (self.getVmObject().getCloneParent() or self.getVmObject().getCloneChildren()):
            raise MCVirtException('Cannot increase the disk of a cloned VM or a clone.')

        command_args = ('lvextend', '-L', '+%sM' % increase_size,
                        self.getConfigObject()._getDiskPath())
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise MCVirtException("Error whilst extending logical volume:\n" + str(e))

    def _checkExists(self):
        """Checks if a disk exists, which is required before any operations
        can be performed on the disk"""
        Local._ensureLogicalVolumeExists(
            self.getConfigObject(),
            self.getConfigObject()._getDiskName())
        return True

    def _removeStorage(self):
        """Removes the backing logical volume"""
        self._ensureExists()
        Local._removeLogicalVolume(self.getConfigObject(), self.getConfigObject()._getDiskName())

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensureExists()
        return Local._getLogicalVolumeSize(
            self.getConfigObject(),
            self.getConfigObject()._getDiskName())

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        self._ensureExists()
        new_disk_config = ConfigLocal(
            vm_object=destination_vm_object,
            disk_id=self.getConfigObject().getId(),
            driver=self.getConfigObject()._getDriver())
        new_logical_volume_name = new_disk_config._getDiskName()
        disk_size = self.getSize()

        # Perform a logical volume snapshot
        command_args = ('lvcreate', '-L', '%sM' % disk_size, '-s',
                        '-n', new_logical_volume_name, self.getConfigObject()._getDiskPath())
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise MCVirtException("Error whilst cloning disk logical volume:\n" + str(e))

        Local._addToVirtualMachine(new_disk_config)

        new_disk_object = Local(destination_vm_object, self.getConfigObject().getId())
        return new_disk_object

    @staticmethod
    def create(vm_object, size, driver, disk_id=None):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        disk_config_object = ConfigLocal(vm_object=vm_object, disk_id=disk_id, driver=driver)
        disk_path = disk_config_object._getDiskPath()
        logical_volume_name = disk_config_object._getDiskName()

        # Ensure the disk doesn't already exist
        if (os.path.lexists(disk_path)):
            raise MCVirtException('Disk already exists: %s' % disk_path)

        # Create the raw disk image
        Local._createLogicalVolume(disk_config_object, logical_volume_name, size)

        # Attach to VM and create disk object
        Local._addToVirtualMachine(disk_config_object)
        disk_object = Local(vm_object, disk_config_object.getId())
        return disk_object

    def activateDisk(self):
        """Starts the disk logical volume"""
        self._ensureExists()
        Local._activateLogicalVolume(self.getConfigObject(), self.getConfigObject()._getDiskName())

    def deactivateDisk(self):
        """Deactivates the disk loglcal volume"""
        self._ensureExists()
        pass

    def preMigrationChecks(self):
        """Perform pre-migration checks"""
        raise CannotMigrateLocalDiskException('VMs using local disks cannot be migrated')

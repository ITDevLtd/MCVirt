# Copyright (c) 2016 - Matt Comben
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


class File(Base):
    """Provides operations to manage local hard drives, used by VMs"""

    MAXIMUM_DEVICES = 4
    CACHE_MODE = 'directsync'

    def __init__(self, file_path=file_path, *args, **kwargs):
        """Set member variables and obtains libvirt domain object"""
        self._file_path = file_path
        super(File, self).__init__(*args, **kwargs)

    @property
    def file_path(self):
        if self._file_path:
            return self._file_path
        raise FilePathNotSetException('File path for disk has not been set')

    @property
    def config_properties(self):
        """Return the disk object config items"""
        return super(File, self).config_properties + ['file_path']

    @staticmethod
    def isAvailable(pyro_object):
        """Determine if local storage is available on the node"""
        return True

    def _check_exists(self):
        """Checks if a disk exists, which is required before any operations
        can be performed on the disk"""
        self._ensureLogicalVolumeExists(
            self._getDiskName())
        return True

    def _removeStorage(self):
        """Do not remove the file"""
        self._ensure_exists()
        os.unlink(self.path)

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensure_exists()
        return self._get_file_size(self.path)

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
        return self.path

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

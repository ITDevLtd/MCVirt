# Copyright (c) 2018 - I.T. Dev Ltd
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

from mcvirt.storage.base import Base, BaseVolume
from mcvirt.exceptions import (InvalidStorageConfiguration,
                               VolumeAlreadyExistsError,
                               DDCommandError, VolumeDoesNotExistError,
                               ExternalStorageCommandErrorException)
from mcvirt.system import System


class File(Base):
    """Storage backend for file based storage"""

    @staticmethod
    def check_exists_local(directory):
        """Determine if the directory actually exists on the node."""
        return os.path.isdir(directory)

    @classmethod
    def ensure_exists(cls, location):
        """Ensure that the volume group exists"""
        if not cls.check_exists(location):
            raise InvalidStorageConfiguration(
                'Directory %s does not exist' % location
            )

    @property
    def _volume_class(self):
        """Return the volume class for the storage backend"""
        return FileVolume

    def get_free_space(self):
        """Return the free space in megabytes."""
        # Obtain statvfs object
        statvfs = os.statvfs(self.get_location())

        # Calculate free space in bytes by multiplying number
        # of available blocks (free for non-superuser) and the
        # block size
        free_space_b = statvfs.f_bavail * statvfs.f_frsize

        # Convert bytes to megabytes
        free_space_mb = float(free_space_b) / (1024 ** 2)

        return free_space_mb


class FileVolume(BaseVolume):
    """Object for handling file volume functions"""

    def get_path(self, node=None):
        """Return the full path of a given volume"""
        return self.storage_backend.get_location(node=node) + '/' + self.name

    def create(self, size):
        """Create volume in storage backend"""
        # Ensure volume does not already exist
        if self.check_exists():
            raise VolumeAlreadyExistsError('Volume (%s) already exists' % self.name)

        try:
            # Create on local node
            System.perform_dd(source=System.WIPE, destination=self.get_path(),
                              size=size)

        except DDCommandError, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst creating disk logical volume:\n" + str(exc)
            )

    def delete(self, ignore_non_existent=False):
        """Delete volume"""
        # Determine if logical volume exists before attempting to remove it
        if not self.check_exists() and not ignore_non_existent:
            raise VolumeDoesNotExistError(
                'Volume (%s) does not exist' % self.name
            )

        try:
            os.unlink(self.get_path())

        except Exception, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst removing logical volume:\n" + str(exc)
            )

    def activate(self):
        """Activate volume"""
        # Ensure volume exists
        self.ensure_exists()

        # Otherwise, do nothing, as files do not
        # need activating
        return

    def is_active(self):
        """Return whether volume is activated"""
        return self.check_exists()

    def snapshot(self, destination_volume, size):
        """Snapshot volume"""
        # Ensure volume exists
        self.ensure_exists()
        System.runCommand(['lvcreate', '--snapshot', self.get_path(),
                           '--name', destination_volume.name,
                           '--size', size])

    def deactivate(self):
        """Deactivate volume"""
        raise NotImplementedError

    def resize(self, size, increase=True):
        """Reszie volume"""
        # Ensure volume exists
        self.ensure_exists()

        raise NotImplementedError

    def check_exists(self):
        """Determine whether logical volume exists"""
        return os.path.exists(self.get_path())

    def get_size(self):
        """Obtain the size of a logical volume"""
        self.ensure_exists()

        # Obtain size from os stat (in bytes)
        size_b = os.stat(self.get_path())

        # Convert size in bytes to megabytes
        size_mb = float(size_b) / (1024 ** 2)

        return size_mb


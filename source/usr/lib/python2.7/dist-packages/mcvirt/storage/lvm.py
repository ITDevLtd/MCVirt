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
from mcvirt.exceptions import (InvalidStorageConfiguration, InvalidNodesException,
                               ExternalStorageCommandErrorException,
                               MCVirtCommandException)
from mcvirt.system import System
from mcvirt.constants import DirectoryLocation


class Lvm(Base):
    """Storage backend for LVM based storage"""

    @classmethod
    def ensure_exists(cls, location):
        """Ensure that the volume group exists"""
        if not cls.check_exists(location):
            raise InvalidStorageConfiguration(
                'Volume group %s does not exist' % location
            )

    @staticmethod
    def _check_exists_local(volume_group):
        """Determine if the volume group actually exists on the node."""
        _, out, _ = System.runCommand(['vgs', '|', 'grep', volume_group],
                                      False, DirectoryLocation.BASE_STORAGE_DIR)
        return bool(out)

    def get_free_space(self):
        """Return the free space in megabytes."""
        _, out, _ = System.runCommand(['vgs', self.get_location(),
                                       '-o', 'free', '--noheadings', '--nosuffix', '--units',
                                       'm'], False,
                                      DirectoryLocation.BASE_STORAGE_DIR)
        return float(out)

    def get_location(self, node=None):
        """Return volume group name for the local host"""
        if node is None:
            node = self._get_registered_object('cluster').get_local_hostname()
        storage_config = self.get_config()
        if node in storage_config['nodes'] and 'location' in storage_config['nodes'][node]:
            return storage_config['nodes']['location']
        elif storage_config['location']:
            return storage_config['location']
        else:
            raise InvalidNodesException('Storage %s not defined on %s' % (self.name, node))


class LvmVolume(BaseVolume):
    """Overriden volume object from base"""

    def get_path(self, node=None):
        """Return the full path of a given logical volume"""
        return '/dev/' + self.storage_backend.get_location(node=node) + '/' + self.name

    def create_volume(self, size):
        """Create volume in storage backend"""
        # Create command list
        command_args = ['/sbin/lvcreate',
                        self.storage_backend.get_location(),  # Specify volume group
                        '--name', self.name,
                        '--size', '%sM' % size]
        try:
            # Create on local node
            System.runCommand(command_args)

        except MCVirtCommandException, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst creating disk logical volume:\n" + str(exc)
            )

    def delete_volume(self, ignore_non_existent):
        """Delete volume"""
        # Create command arguments
        command_args = ['lvremove', '-f', self.get_path()]
        try:
            # Determine if logical volume exists before attempting to remove it
            if (not (ignore_non_existent and
                     not self.check_exists())):
                System.runCommand(command_args)

        except MCVirtCommandException, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst removing logical volume:\n" + str(exc)
            )

    def activate_volume(self):
        """Activate volume"""
        # Create command arguments
        command_args = ['lvchange', '-a', 'y', '--yes', self.get_path()]
        try:
            # Run on the local node
            System.runCommand(command_args)

        except MCVirtCommandException, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst activating logical volume:\n" + str(exc)
            )

    def is_volume_activated(self):
        """Return whether volume is activated"""
        return os.path.exists(self.get_path())

    def snapshot_volume(self, destination, size):
        """Snapshot volume"""
        System.runCommand(['lvcreate', '--snapshot', self.get_path(),
                           '--name', destination,
                           '--size', size])

    def deactivate_volume(self):
        """Deactivate volume"""
        raise NotImplementedError

    def resize_volume(self, size):
        """Reszie volume"""
        command_args = ['/sbin/lvresize', '--size', '%sM' % size,
                        self.get_path()]
        try:
            # Create on local node
            System.runCommand(command_args)

        except MCVirtCommandException, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst resizing disk logical volume:\n" + str(exc)
            )

    def check_exists(self):
        """Determine whether logical volume exists"""
        return os.path.lexists(self.get_path())

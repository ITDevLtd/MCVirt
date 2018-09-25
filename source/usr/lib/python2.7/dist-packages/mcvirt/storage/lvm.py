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

from mcvirt.storage.base import Base
from mcvirt.exceptions import (InvalidStorageConfiguration, InvalidNodesException,
                               ExternalStorageCommandErrorException,
                               MCVirtCommandException)
from mcvirt.system import System
from mcvirt.constants import DirectoryLocation


class Lvm(Base):
    """Storage backend for LVM based storage"""

    @classmethod
    def ensure_exists(cls, location):
        if not cls.check_exists(location):
            raise InvalidStorageConfiguration(
                'Volume group %s does not exist' % location
            )

    @staticmethod
    def _check_exists_local(volume_group):
        """Determine if the volume group actually exists on the node."""
        _, out, err = System.runCommand(['vgs', '|', 'grep', volume_group],
                                        False, DirectoryLocation.BASE_STORAGE_DIR)
        return bool(out)

    def get_free_space(self):
        """Returns the free space in megabytes."""
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

    def get_volume_path(self, name, node=None):
        """Return the full path of a given logical volume"""
        return '/dev/' + self.get_location(node=node) + '/' + name

    def create_volume(self, name, size):
        """Create volume in storage backend"""
        volume_group = self.get_location()

        # Create command list
        command_args = ['/sbin/lvcreate', volume_group, '--name', name, '--size', '%sM' % size]
        try:
            # Create on local node
            System.runCommand(command_args)

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst creating disk logical volume:\n" + str(e)
            )

    def delete_volume(self, name, ignore_non_existent):
        """Delete volume"""
        # Create command arguments
        command_args = ['lvremove', '-f', self.get_volume_path(name)]
        try:
            # Determine if logical volume exists before attempting to remove it
            if (not (ignore_non_existent and
                     not self.volume_exists(name))):
                System.runCommand(command_args)

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst removing logical volume:\n" + str(e)
            )

    def activate_volume(self, name):
        """Activate volume"""
        # Obtain logical volume path
        lv_path = self.get_volume_path(name)

        # Create command arguments
        command_args = ['lvchange', '-a', 'y', '--yes', lv_path]
        try:
            # Run on the local node
            System.runCommand(command_args)

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst activating logical volume:\n" + str(e)
            )

    def is_volume_activated(self, name):
        """Return whether volume is activated"""
        return os.path.exists(self.get_volume_path(name))

    def snapshot_volume(self, name, destination, size):
        """Snapshot volume"""
        System.runCommand(['lvcreate', '--snapshot', self.get_volume_path(name),
                           '--name', destination,
                           '--size', size])

    def deactivate_volume(self, name):
        """Deactivate volume"""
        raise NotImplementedError

    def resize_volume(self, name, size):
        """Reszie volume"""
        command_args = ['/sbin/lvresize', '--size', '%sM' % size,
                        self.get_volume_path(name)]
        try:
            # Create on local node
            System.runCommand(command_args)

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst resizing disk logical volume:\n" + str(e)
            )

    def volume_exists(self, name):
        """Determine whether logical volume exists"""
        return os.path.lexists(self.get_volume_path(name))

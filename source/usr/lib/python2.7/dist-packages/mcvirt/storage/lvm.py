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


from mcvirt.storage.base import Base
from mcvirt.exceptions import (InvalidStorageConfiguration, InvalidNodesException,
                               ExternalStorageCommandErrorException,
                               MCVirtCommandException)
from mcvirt.system import System


class Lvm(Base):
    """Storage backend for LVM based storage"""

    @staticmethod
    def node_pre_check(node, cluster, location):
        """Ensure volume group exists on node"""
        if not node.volume_group_exists(location):
            raise InvalidStorageConfiguration(
                'Volume group %s does not exist on node: %s' %
                (location, cluster.get_local_hostname())
            )

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

    def delete_volume(self, name):
        """Delete volume"""
        raise NotImplementedError

    def activate_volume(self, name):
        """Activate volume"""
        raise NotImplementedError

    def is_volume_activated(self, name):
        """Return whether volume is activated"""
        raise NotImplementedError

    def snapshot_volume(self, name, destination, size):
        """Snapshot volume"""
        raise NotImplementedError

    def deactivate_volume(self, name):
        """Deactivate volume"""
        raise NotImplementedError

    def resize_volume(self, name, size):
        """Reszie volume"""
        command_args = ['/sbin/lvresize', '--size', '%sM' % size,
                        self.get_volume_path(name)]


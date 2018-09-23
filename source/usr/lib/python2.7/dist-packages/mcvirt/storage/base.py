"""Provide base operations to manage all hard drives, used by VMs"""
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

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import InvalidNodesException
from mcvirt.utils import get_hostname


class Base(PyroObject):
    """Provides base functionality for storage backends"""

    @property
    def name(self):
        return self._name

    def __init__(self, name):
        """Setup member variables"""
        self._name = name

    @Expose(locking=True)
    def delete(self):
        """Shared function to remove storage"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        # Remove VM from MCVirt configuration
        def updateMCVirtConfig(config):
            config['storage_backends'].remove(self.name)
        MCVirtConfig().update_config(
            updateMCVirtConfig,
            'Removed storage backend \'%s\' from global MCVirt config' %
            self.name)

        # Remove from remote machines in cluster
        if self._is_cluster_master:
            def remote_command(remote_object):
                storage_factory = remote_object.get_connection('storage_factory')
                remote_storage_backend = storage_factory.getVirtualMachineByName(self.name)
                remote_object.annotate_object(remote_storage_backend)
                remote_storage_backend.delete()
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

        # Remove cached pyro object
        storage_factory = self._get_registered_object('storage_factory')
        if self.name in storage_factory.CACHED_OBJECTS:
            del(storage_factory.CACHED_OBJECTS[self.name])

    @staticmethod
    def validate_config(cluster, config):
        """Validate config"""
        # Ensure that all nodes specified are valid
        for node in config['nodes']:
            cluster.ensure_node_exists(node)

    @Expose()
    def get_config(self):
        """Get config for storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        return MCVirtConfig().get_config()['storage_backends'][self.name]

    def set_default_location(self, new_location):
        """Set a new default location for storage backend.
           None will mean no default location"""
        pass

    def add_node(self, node_name, custom_location=None):
        """Add a new node to the storage backend"""
        pass

    def remove_node(self, node_name):
        """Remove a node from the storage backend"""
        pass

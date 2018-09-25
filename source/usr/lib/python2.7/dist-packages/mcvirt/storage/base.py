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
from mcvirt.exceptions import (UnsuitableNodeException,
                               NodeAlreadyConfiguredInStorageBackend,
                               StorageBackendInUse,
                               StorageBackendNotAvailableOnNode,
                               InvalidStorageConfiguration)


class Base(PyroObject):
    """Provides base functionality for storage backends"""

    @property
    def name(self):
        """Return name of storage backend"""
        return self._name

    @property
    def shared(self):
        """Return shared config parameter"""
        return self.get_config()['shared']

    @property
    def nodes(self):
        """Return nodes that the storage is available to"""
        return self.get_config()['nodes'].keys()

    @property
    def storage_type(self):
        """Return storage type for storage backend"""
        return self.__class__.__name__

    def __eq__(self, comp):
        """Allow for comparison of storage objects baesd on name"""
        # Ensure class and name of object match
        if ('__class__' in comp and
                comp.__class__ == self.__class__ and
                'name' in comp and comp.name == self.name):
            return True

        # Otherwise return false
        return False

    def __init__(self, name):
        """Setup member variables"""
        self._name = name

    def in_use(self):
        """Whether the storage backend is used for any disks objects"""
        # Get VM factory
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')

        # Iterate over all virtual machine and hard drive objects
        for vm in virtual_machine_factory.getAllVirtualMachines():
            for hard_drive in vm.getHardDriveObjects():

                # If the hard drive object uses the current storage backend,
                # return True
                if hard_drive.get_storage_backend() == self:
                    return True
        # If no matches have been found, return False
        return False

    @Expose(locking=True)
    def delete(self):
        """Shared function to remove storage"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        # Determine if storage backend if used by VMs
        if self.in_use():
            raise StorageBackendInUse('Storage backend cannot be removed as it is used by VMs')

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
                """Delete backend storage from remote nodes"""
                storage_factory = remote_object.get_connection('storage_factory')
                remote_storage_backend = storage_factory.getVirtualMachineByName(self.name)
                remote_object.annotate_object(remote_storage_backend)
                remote_storage_backend.delete()
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

        # Remove cached pyro object
        storage_factory = self._get_registered_object('storage_factory')
        if self.name in storage_factory.CACHED_OBJECTS:
            del storage_factory.CACHED_OBJECTS[self.name]

    @staticmethod
    def validate_config(cluster, config):
        """Validate config"""
        # Ensure that all nodes specified are valid
        for node in config['nodes']:
            cluster.ensure_node_exists(node, include_local=True)

    @Expose()
    def get_config(self):
        """Get config for storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        return MCVirtConfig().get_config()['storage_backends'][self.name]

    @Expose()
    def set_location(self, new_location, node=None):
        """Set a new location for storage backend.
        None will mean no default location
        If node is set to None, the default location will be set
        """
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)
        pass

    @Expose()
    def add_node(self, node_name, custom_location=None):
        """Add a new node to the storage backend"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        location = custom_location if custom_location else self.get_location()

        # Ensure node is not already attached to storage backend
        if node_name in self.nodes:
            raise NodeAlreadyConfiguredInStorageBackend(
                'Node already configured in storage backend: %s %s' % node_name, self.name
            )

        cluster = self._get_registered_object('cluster')

        # If adding local node to cluster
        if node_name == cluster.get_local_hostname():

            # Ensure that the requested volume exists
            storage_factory = self._get_registered_object('storage_factory')
            storage_factory.node_pre_check(storage_type=self.storage_type,
                                           location=location)
        else:
            def remote_command(connection):
                remote_storage_factory = connection.get_connection('storage_factory')
                remote_storage_factory.node_pre_check(storage_type=self.storage_type,
                                                      location=location)

    @Expose()
    def remove_node(self, node_name):
        """Remove a node from the storage backend"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

    def get_location(self, node=None):
        """Return the location for a given node, default to local node"""
        if node is None:
            cluster = self._get_registered_object('cluster')
            node = cluster.get_local_hostname()
        if node not in self.nodes:
            raise UnsuitableNodeException(
                'Node does not support storage backend: %s, %s' % (node, self.name)
            )
        config = self.get_config()
        return (config['nodes'][node]['location'] if config['nodes'][node]['location']
                else config['nodes']['location'])

    def ensure_available_on_node(self, node=None):
        """Check if the storage backend is not available on the given node and
        raise an exception
        """
        if node is None:
            cluster = self._get_registered_object('cluster')
            node = cluster.get_local_hostname()
        if not self.available_on_node(node=node):
            raise StorageBackendNotAvailableOnNode(
                'Storage not available on node: %s, %s' % (self.name, node)
            )

    def available_on_node(self, node=None):
        """Determine if the storage volume is available on
        a given node
        """
        if node is None:
            cluster = self._get_registered_object('cluster')
            node = cluster.get_local_hostname()
        return node in self.nodes

    @classmethod
    def node_pre_check(cls, cluster, location):
        """Ensure volume group exists on node"""
        try:
            cls.ensure_exists(location)
        except InvalidStorageConfiguration, exc:
            raise InvalidStorageConfiguration(
                '%s on node %s' % (str(exc), cluster.get_local_hostname())
            )

    def is_drbd_suitable(self):
        """Return boolean depending on whether storage backend is suitable to be
        used for backing DRBD
        """
        return not self.shared

    @classmethod
    def ensure_exists(cls, location):
        """Ensure that the underlying storage exists"""
        raise NotImplementedError

    def check_exists(self):
        """Check volume groups exists on the local node"""
        return self.__class__._check_exists_local(self.get_location())

    @classmethod
    def _check_exists_local(cls, location):
        """Determine if underlying storage actually exists on the node."""
        raise NotImplementedError

    def get_free_space(self):
        """Return the amount of free spacae in the storage backend"""
        raise NotImplementedError


class BaseVolume(object):
    """Base class for handling volume actions.
    These classes do NOT care about a virtual machine,
    only about performing necessary commands to manipulate a
    disk on the system
    """

    @property
    def name(self):
        """Return the name of the volume"""
        return self._name

    @property
    def storage_backend(self):
        """Return the storage backend"""
        return self._storage_backend

    def __init__(self, name, storage_backend):
        """Setup vairables"""
        self._name = name
        self._storage_backend = storage_backend

    def create_volume(self, size):
        """Create volume in storage backend"""
        raise NotImplementedError

    def delete_volume(self, ignore_non_existent):
        """Delete volume"""
        raise NotImplementedError

    def activate_volume(self):
        """Activate volume"""
        raise NotImplementedError

    def is_volume_activated(self):
        """Return whether volume is activated"""
        raise NotImplementedError

    def snapshot_volume(self, destination, size):
        """Snapshot volume"""
        raise NotImplementedError

    def deactivate_volume(self):
        """Deactivate volume"""
        raise NotImplementedError

    def resize_volume(self, size):
        """Reszie volume"""
        raise NotImplementedError

    def volume_exists(self):
        """Determine whether volume exists"""
        raise NotImplementedError

    def get_size(self):
        """Obtain the size of the volume"""
        raise NotImplementedError

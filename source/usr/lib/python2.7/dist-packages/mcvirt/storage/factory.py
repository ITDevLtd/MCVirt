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


from mcvirt.storage.lvm import Lvm
from mcvirt.storage.file import File
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.constants import DEFAULT_STORAGE_NAME
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.exceptions import (UnknownStorageTypeException, StorageBackendDoesNotExist,
                               InvalidStorageConfiguration)
from mcvirt.argument_validator import ArgumentValidator


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects"""

    STORAGE_TYPES = [Lvm, File]
    OBJECT_TYPE = 'storage backend'
    CACHED_OBJECTS = {}

    def v9_release_upgrade(self):
        """As part of the version 9 release. The configuration
           update cannot be performed whilst the cluster is down
           (i.e. during startup).
           During start up, an initial configuration change to implement
           the default storage backend (as an upgrade from the 'vm_storage_vg'
           configuration) is created with just the local node specified.
           Once the node is started, this function is called, which determines
           if the rest of the cluster is active (so will make any changes on the
           final node to be started with >=v9.0.0 running). It will then
           look at the rest of the cluster to determine if the same volume group
           is used on a majority of the cluster (to determine if a default VG is
           appropriate for the storage) and then re-configure the 'default' storage
           backend on all nodes in the cluster."""

        # Determine if storage has already been configured
        if MCVirtConfig().get_config()['default_storage_configured']:
            return

        def mark_storage_configured(config):
            config['default_storage_configured'] = True

        # If default storage backend has already been reconfigured, or there is no 'default'
        # storage backend because 'vm_storage_vg' was never set, return
        try:
            default_storage = self.get_object('default')
        except StorageBackendDoesNotExist:
            # Storage backend does not exist, mark default storage as being configured
            # and return
            MCVirtConfig().update_config(
                mark_storage_configured,
                'Default storage configuration complete'
            )

        # Setup variables for configuration
        nodes = []
        # With the old method of storage, without DRBD, storage was never
        # usable in a shared fashion, so assume that it is not.
        shared = False
        # Use a constant for the name of the storage
        name = DEFAULT_STORAGE_NAME
        # Define default_vg_name
        default_vg_name = None

        # Get cluster object
        cluster = self._get_registered_object('cluster')

        # If there is one node in the cluster, we can continue configuring the node
        if (not cluster.get_nodes(return_all=True)):
            # Single node cluster
            default_vg_name = 

        else:
            # Otherwise, perform a version check on the cluster, which will determine if
            # either all nodes in the cluster are running and that all nodes
            # are running the new version
            try:
                cluster.check_node_versions()
            except (CouldNotConnectToNodeException, NodeVersionMismatch):
                # If nodes are unavailable or running different versions of code, return
                return

    @Expose(locking=True)
    def create(self, name, storage_type, location, shared=False,
               nodes={}):
        """Create storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANGAE_STORAGE)

        # Ensure that either:
        # a default location is defined
        # all nodes provide an override location
        if (not location and
                None in [nodes[node]['location'] if 'location' in nodes[node] else None
                         for node in nodes]):
            raise InvalidStorageConfiguration(('A default location has not been set and '
                                               'some nodes do not have an override set'))

        storage_class = self.get_class(storage_type)

        if self._is_cluster_master:
            # If no nodes have been specified, get all nodes in cluster
            if not nodes:
                cluster_object = self._get_registered_object('cluster')
                nodes = {
                    node: {'location': None}
                    for node in cluster_object.get_nodes(return_all=True, include_local=True)
                }

        # Create config
        config = {'storage_type': storage_type,
                  'shared': shared,
                  'nodes': nodes,
                  'location': location}

        if self._is_cluster_master:
            # Ensure that config requirements and system requirements
            # are as expected for the type of storage backend
            # Only required on cluster master, as this checks all nodes in the cluster
            storage_class.validate_config(
                self._get_registered_object('node'),
                self._get_registered_object('cluster'),
                config
            )

        # Add new storage backend to MCVirt config
        def update_config(mcvirt_config):
            mcvirt_config['storage_backends'][name] = config
        MCVirtConfig().update_config(update_config, 'Add storage backend %s' % name)

        if self._is_cluster_master:
            def remote_command(remote_connection):
                storage_factory = remote_connection.get_connection('storage_factory')
                storage_factory.create(name=name, storage_type=storage_type,
                                       location=location, shared=shared,
                                       nodes=nodes)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    def get_config(self):
        """Return the configs for storage backends"""
        return MCVirtConfig().get_config()['storage_backends']

    def check_exists(self, name):
        """Determine if a storage backend exists"""
        return (name in self.get_config().keys())

    @Expose()
    def get_object(self, name):
        """Returns the storage object for a given disk"""
        # Get config for storage backend
        storage_backends_config = MCVirtConfig().get_config()['storage_backends']
        if (name not in storage_backends_config.keys() or
                'type' not in storage_backends_config[name]):
            raise StorageBackendDoesNotExist('Storage backend does not exist or is mis-configured')
        storage_type = storage_backends_config[name]['type']

        # Create required storage object, based on type
        if name not in Factory.CACHED_OBJECTS:
            storage_object = self.get_class(storage_type)(name)
            self._register_object(storage_object)
            Factory.CACHED_OBJECTS[name] = storage_object

        return Factory.CACHED_OBJECTS[name]

    def get_storage_types(self):
        """Returns the available storage types that MCVirt provides"""
        return self.STORAGE_TYPES

    def get_class(self, storage_type):
        """Obtains the storage class for a given storage type"""
        for storage_class in self.get_storage_types():
            if (storage_type == storage_class.__name__):
                return storage_class
        raise UnknownStorageTypeException(
            'Attempted to initialise an unknown storage type: %s' %
            (storage_type)
        )

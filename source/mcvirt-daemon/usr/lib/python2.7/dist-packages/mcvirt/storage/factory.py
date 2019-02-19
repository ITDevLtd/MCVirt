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

from texttable import Texttable

from mcvirt.storage.lvm import Lvm
from mcvirt.storage.file import File
from mcvirt.storage.base import Base
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.constants import DEFAULT_STORAGE_NAME, DEFAULT_STORAGE_ID
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose, Transaction
from mcvirt.exceptions import (UnknownStorageTypeException, StorageBackendDoesNotExist,
                               InvalidStorageConfiguration, InaccessibleNodeException,
                               NodeVersionMismatch, StorageBackendAlreadyExistsError)
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.utils import convert_size_friendly, get_all_submodules, get_hostname
from mcvirt.config.storage import Storage as StorageConfig
from mcvirt.size_converter import SizeConverter


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects."""

    STORAGE_TYPES = [Lvm, File]
    OBJECT_TYPE = 'storage backend'
    CACHED_OBJECTS = {}
    STORAGE_CONFIG_KEY = 'storage_backends'

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the current storage backend object on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('storage_factory')

    @Expose()
    def get_all(self, available_on_local_node=None, nodes=[], drbd=None,
                storage_type=None, shared=None, nodes_predefined=False,
                global_=None, default_location=None):
        """Return all storage backends, with optional filtering."""
        storage_objects = []

        for storage_id in self.get_config().keys():

            # Obtain storage object
            storage_object = self.get_object(storage_id)

            # Check if storage backend is global or not
            if global_ is not None and storage_object.is_global != global_:
                continue

            # Check if default location matches requested
            if (default_location is not None and
                    storage_object.get_location(return_default=True) != default_location):
                continue

            # Check storage is available on local node
            if (available_on_local_node and
                    get_hostname() not in storage_object.nodes):
                continue

            # If nodes are specified...
            if nodes:
                # Determine which nodes from the list are available
                available_nodes = []
                for node in nodes:
                    if node in storage_object.nodes:
                        available_nodes.append(node)

                # If the list of nodes is required (predefined) and not all are
                # present, skip storage backend
                if nodes_predefined and len(nodes) != len(available_nodes):
                    continue

                # Otherwise, (if the nodes are not required), ensure at least one
                # is available, otherwise, skip
                elif (not nodes_predefined) and not len(available_nodes):
                    continue

            # If drbd is specified, ensure storage object is suitable to run DRBD
            if drbd and not storage_object.is_drbd_suitable():
                continue

            # If storage_type is specified, ensure hat storage matches the object
            if storage_type and not self.get_class(storage_type) != storage_object.__class__:
                continue

            # If a shared type is defined, determine if it matches the object, otherwise skip
            if shared is not None and shared != storage_object.shared:
                continue

            # If all checks have passed, append to list of objects to return
            storage_objects.append(storage_object)

        return storage_objects

    @Expose()
    def validate_config(self, storage_type, config):
        """Perform the class method validate_config."""
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)
        return self.get_class(storage_type).validate_config(
            cluster=self.po__get_registered_object('cluster'),
            config=config
        )

    @Expose(locking=True)
    def create(self, name, storage_type, location, shared=False, id_=None,
               node_config={}):
        """Create storage backend."""
        # Check permissions
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        # Ensure storage backend does not already exist with same name
        if self.get_id_by_name(name):
            raise StorageBackendAlreadyExistsError('Storage backend already exists: %s' % name)

        t = Transaction()

        # Ensure that nodes are valid
        cluster = self.po__get_registered_object('cluster')

        for node in node_config:
            cluster.ensure_node_exists(node, include_local=True)

        # Ensure that either:
        # a default location is defined
        # all nodes provide an override location
        if (not location and
                (None in [node_config[node]['location']
                          if 'location' in node_config[node] else None
                          for node in node_config] or
                 not node_config)):
            raise InvalidStorageConfiguration(('A default location has not been set and '
                                               'some nodes do not have an override set'))

        storage_class = self.get_class(storage_type)

        # Generate ID for the storage backend
        id_ = storage_class.generate_id(name)

        # Ensure name is valid
        ArgumentValidator.validate_storage_name(name)

        # Get all locations and verify that the names are valid
        # @TODO - Refactor this to be more readable
        for location_itx in [] if not location else [location] + \
                [node_config[node]['location']
                 if 'location' in node_config[node]
                 else None
                 for node in node_config]:
            if location_itx is not None:
                storage_class.validate_location_name(location_itx)

        # If no nodes have been specified, get all nodes in cluster
        if not node_config:
            cluster = self.po__get_registered_object('cluster')
            node_config = {
                node: {'location': None}
                for node in cluster.get_nodes(return_all=True, include_local=True)
            }

        # Create config
        config = {'name': name,
                  'type': storage_type,
                  'shared': shared,
                  'nodes': node_config,
                  'location': location}

        # Ensure that config requirements and system requirements
        # are as expected for the type of storage backend
        # Only required on cluster master, as this checks all nodes in the cluster
        self.validate_config(
            storage_type=storage_type,
            config=config
        )

        # Ensure pre-requisites for storage backend pass on each node
        for node in node_config:
            node_location = (node_config[node]['location']
                             if 'location' in node_config[node] and
                             node_config[node]['location'] is not None else location)

            self.node_pre_check(location=node_location, storage_type=storage_type,
                                nodes=[node])

        self.create_config(id_, config, nodes=cluster.get_nodes(include_local=True))

        storage_object = self.get_object(id_)

        # Create ID volume
        storage_object.create_id_volume()

        t.finish()

        return storage_object

    @Expose(remote_nodes=True)
    def create_config(self, id_, config):
        """Create config for the storage backend."""
        StorageConfig.create(id_, config)

    @Expose()
    def undo__create_config(self, id_, config):
        """Undo the create config."""
        def update_config(mcvirt_config):
            """Update MCVirt config."""
            del mcvirt_config['storage_backends'][id_]
        MCVirtConfig().update_config(update_config, 'Remove storage backend %s' % config['name'])

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses."""
        # Set permissions as having been checked, as listing VMs
        # does not require permissions
        self.po__get_registered_object('auth').set_permission_asserted()

        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Name', 'Type', 'Location', 'Nodes', 'Shared', 'Free Space', 'ID'))

        # Set column alignment and widths
        table.set_cols_width((15, 5, 30, 70, 6, 15, 50))
        table.set_cols_align(('l', 'l', 'l', 'l', 'l', 'l', 'l'))

        for storage_backend in self.get_all():
            table.add_row((
                storage_backend.name,
                storage_backend.storage_type,
                storage_backend.get_location(),
                ', '.join(storage_backend.nodes),
                str(storage_backend.shared),
                SizeConverter(storage_backend.get_free_space()).to_string(),
                storage_backend.id_
            ))
        return table.draw()

    @Expose(remote_nodes=True)
    def node_pre_check(self, location, storage_type):
        """Ensure node is suitable for storage backend."""
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)
        cluster = self.po__get_registered_object('cluster')
        libvirt_config = self.po__get_registered_object('libvirt_config')
        self.get_class(storage_type).node_pre_check(cluster=cluster,
                                                    libvirt_config=libvirt_config,
                                                    location=location)

    def get_config(self):
        """Return the configs for storage backends."""
        return StorageConfig.get_global_config()

    def get_id_by_name(self, name):
        """Determine the ID of a storage backend by name."""
        config = self.get_config()

        # Check each
        for id_ in config:
            if config[id_]['name'] == name:
                return id_

        # Return False if it does not exist
        return False

    def check_exists(self, id_):
        """Determine if a storage backend exists by ID."""
        return id_ in self.get_config().keys()

    @Expose()
    def get_object(self, id_):
        """Return a storage backend object."""
        # Get config for storage backend
        storage_backends_config = self.get_config()

        # Ensure exists and config is valid
        if not self.check_exists(id_):
            raise StorageBackendDoesNotExist('Storage backend does not exist: %s' % id_)

        # Obtain storage type from config
        storage_type = storage_backends_config[id_]['type']

        # Create required storage object, based on type
        if id_ not in Factory.CACHED_OBJECTS:
            storage_object = self.get_class(storage_type)(id_)
            self.po__register_object(storage_object)
            Factory.CACHED_OBJECTS[id_] = storage_object

        return Factory.CACHED_OBJECTS[id_]

    @Expose()
    def get_object_by_name(self, name):
        """Return a storage object by name."""
        object_id = self.get_id_by_name(name)
        if not object_id:
            raise StorageBackendDoesNotExist('Storage backend does not exist: %s' % name)
        return self.get_object(object_id)

    def get_storage_types(self):
        """Return the available storage types that MCVirt provides."""
        return get_all_submodules(Base)

    def get_class(self, storage_type):
        """Obtain the storage class for a given storage type."""
        for storage_class in self.get_storage_types():
            if storage_type == storage_class.__name__:
                return storage_class
        raise UnknownStorageTypeException(
            'Attempted to initialise an unknown storage type: %s' %
            (storage_type)
        )

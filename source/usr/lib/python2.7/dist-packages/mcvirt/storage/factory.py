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
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.constants import DEFAULT_STORAGE_NAME, DEFAULT_STORAGE_ID
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.exceptions import (UnknownStorageTypeException, StorageBackendDoesNotExist,
                               InvalidStorageConfiguration, InaccessibleNodeException,
                               NodeVersionMismatch, StorageBackendAlreadyExistsError)
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.utils import convert_size_friendly, get_all_submodules, get_hostname


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects"""

    STORAGE_TYPES = [Lvm, File]
    OBJECT_TYPE = 'storage backend'
    CACHED_OBJECTS = {}
    STORAGE_CONFIG_KEY = 'storage_backends'

    def initialise(self):
        """Perform any post-startup tasks"""
        # Perform v9.0.0 configuration upgrade
        self.v9_release_upgrade()
        # Perform any parent tasks
        super(Factory, self).initialise()

    def v9_release_upgrade(self):
        """As part of the version 9.0.0 release. The configuration
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
        backend on all nodes in the cluster.
        """

        # Determine if storage has already been configured
        if MCVirtConfig().get_config()['default_storage_configured']:
            return

        # Get cluster object
        cluster = self._get_registered_object('cluster')

        # Perform a version check on the cluster, which will determine if
        # either all nodes in the cluster are running and that all nodes
        # are running the new version
        try:
            cluster.check_node_versions()
        except (InaccessibleNodeException, NodeVersionMismatch):
            # If nodes are unavailable or running different versions of code, return
            return

        # Setup variables for configuration
        nodes = {}
        # With the old method of storage, without DRBD, storage was never
        # usable in a shared fashion, so assume that it is not.
        shared = False

        # Define default_vg_name
        default_vg_name = None

        # Attempt to obtain local instance of default storage. Ignore if there is no 'default'
        # storage backend because 'vm_storage_vg' was never set.
        try:
            local_storage_object = self.get_object_by_name(DEFAULT_STORAGE_NAME)

            # Get the configuration for each of the nodes
            local_storage_config = local_storage_object.get_config()
            current_node_configs = {
                get_hostname(): local_storage_config['nodes'][
                    get_hostname()
                ]
            }
        except StorageBackendDoesNotExist:
            # Storage backend does not exist, continue anyway, as other nodes
            # may need configuring
            pass

        def get_remote_config(connection):
            storage_factory = connection.get_connection('storage_factory')
            # Get the remote node's storage object
            try:
                default_object = storage_factory.get_object(DEFAULT_STORAGE_ID)
            except StorageBackendDoesNotExist:
                return
            connection.annotate_object(default_object)
            node_config = default_object.get_config()

            # Get the node's node configuration from the node's config for the
            # storage backend
            current_node_configs[connection.name] = node_config['nodes'][connection.name]
        cluster.run_remote_command(get_remote_config)

        # If no nodes have storage configured, mark storage as having been configured and return
        if not len(current_node_configs):
            self.set_default_v9_release_config(None)
            return

        # Get volume groups and convert to list to get unique values
        unique_volume_groups = set([current_node_configs[node]['location']
                                    for node in current_node_configs])

        # If there is just one volume group acros the cluster, set the default volume group to this
        if len(unique_volume_groups) == 1:
            default_vg_name = list(unique_volume_groups)[0]
            nodes = {node: {'location': None} for node in current_node_configs}
        else:
            nodes = {node: {'location': current_node_configs[node]['location']}
                     for node in current_node_configs}

        storage_config = {
            'nodes': nodes,
            'shared': shared,
            'location': default_vg_name,
            'type': Lvm.__name__
        }
        self.set_default_v9_release_config(storage_config)

        # Obtain the default storage backend
        storage_backend = self.get_object(DEFAULT_STORAGE_ID)

        # Go through each of the VMs to update config for new storage backends
        for virtual_machine in (self._get_registered_object(
                'virtual_machine_factory').getAllVirtualMachines()):

            # Obtain the VM config object and config
            vm_config_object = virtual_machine.get_config_object()
            config = vm_config_object.get_config()
            new_storage_config = {}

            # Iterate through each of the disks to update the config
            for disk_id in config['hard_disks'].keys():
                # Determine if a custom volume group has been used
                # for the VM
                if 'custom_volume_group' in config['hard_disks'][disk_id]:
                    # Attempt to find storage backend that provides
                    # the custom volume group
                    custom_storage_backends = self.get_all(
                        storage_type=Lvm.__name__,
                        default_location=config['hard_disks'][disk_id]['custom_volume_group'])

                    # If no storage backends match the location, create one:
                    if not custom_storage_backends:
                        # Determine a free name for the storage backend
                        #  Setup iterator for name
                        itx = 1
                        # Default the name to the volume group name
                        custom_storage_backend_name = \
                            config['hard_disks'][disk_id]['custom_volume_group']

                        while True:
                            # Determine if the name is free, if so break
                            if not self.get_id_by_name(custom_storage_backend_name):
                                break

                            # Otherwise, update name and increment iterator
                            custom_storage_backend_name = '%s-%i' % (
                                config['hard_disks'][disk_id]['custom_volume_group'],
                                itx
                            )

                        # Once name is obtained, create the storage backend.
                        # Set name, use LVM as storage type, set location to volume group,
                        # disable sharing and set nodes to the list of available nodes
                        # of the VM, since, it must exist on all of these, in theory...
                        custom_storage_backend = self.create(
                            name=custom_storage_backend_name,
                            storage_type=Lvm.__name__,
                            location=config['hard_disks'][disk_id]['custom_volume_group'],
                            shared=False,
                            node_config={node: {'location': None}
                                         for node in config['available_nodes']})

                    else:
                        # Otherwise, if a storage backend was found...
                        custom_storage_backend = custom_storage_backends[0]
                        # Ensure that all of the nodes that the VM was available to
                        # are in the list of nodes for the storage backend, otherwise
                        # add them.
                        for node in config['available_nodes']:
                            if node not in custom_storage_backend.nodes:
                                custom_storage_backend.add_node(node)

                else:
                    # Otherwise, if custom volume group was not defined, used the default one
                    custom_storage_backend = storage_backend

                # Update disk config, adding the parameter for storage_backend
                new_storage_config[disk_id] = custom_storage_backend.id_

            # Update the VM config on the local and remote nodes
            virtual_machine.set_v9_release_config(new_storage_config)

    @Expose(locking=True)
    def set_default_v9_release_config(self, config):
        """Update default storage config across cluster"""
        # Check permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        def update_config(mcvirt_config):
            """Update config for default storage"""
            if config:
                # Update config for default storage
                mcvirt_config[Factory.STORAGE_CONFIG_KEY][DEFAULT_STORAGE_ID] = config

            # If config is None and default storage backend exists in config, remove it.
            elif (config is None and
                    DEFAULT_STORAGE_ID in mcvirt_config[Factory.STORAGE_CONFIG_KEY]):
                del mcvirt_config[Factory.STORAGE_CONFIG_KEY][DEFAULT_STORAGE_ID]

            # Mark default config as having been configured
            mcvirt_config['default_storage_configured'] = True

        self._get_registered_object('mcvirt_config')().update_config(
            update_config,
            'Update default storage for v9.0.0 upgrade'
        )

        if self._is_cluster_master:
            # If cluster master, update the remote nodes
            def update_remote_config(remote_connection):
                storage_factory = remote_connection.get_connection('storage_factory')
                storage_factory.set_default_v9_release_config(config)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(update_remote_config)

    @Expose()
    def get_all(self, available_on_local_node=None, nodes=[], drbd=None,
                storage_type=None, shared=None, nodes_predefined=False,
                global_=None, default_location=None):
        """Return all storage backends, with optional filtering"""
        storage_objects = []
        cluster = self._get_registered_object('cluster')

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
        """Perform the class method validate_config"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)
        return self.get_class(storage_type).validate_config(
            cluster=self._get_registered_object('cluster'),
            config=config
        )

    @Expose(locking=True)
    def create(self, name, storage_type, location, shared=False, id_=None,
               node_config={}):
        """Create storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        # Only perform checks and config manipulation on cluster master (so that it's
        # only run once)
        if self._is_cluster_master:
            # Ensure storage backend does not already exist with same name
            if self.get_id_by_name(name):
                raise StorageBackendAlreadyExistsError('Storage backend already exists: %s' % name)

            # Ensure that nodes are valid
            cluster = self._get_registered_object('cluster')

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
                cluster = self._get_registered_object('cluster')
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

        if self._is_cluster_master:
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

                if node == get_hostname():
                    self.node_pre_check(location=node_location, storage_type=storage_type)
                else:
                    # If node is a remote node, run the command remotely
                    def remote_command(connection):
                        """Perform remote node_pre_check command"""
                        storage_factory = connection.get_connection('storage_factory')
                        storage_factory.node_pre_check(location=node_location,
                                                       storage_type=storage_type)
                    cluster.run_remote_command(remote_command, node=node)

        # Add new storage backend to MCVirt config
        def update_config(mcvirt_config):
            """Update MCVirt config"""
            mcvirt_config['storage_backends'][id_] = config
        MCVirtConfig().update_config(update_config, 'Add storage backend %s' % name)

        if self._is_cluster_master:
            def remote_create(remote_connection):
                """Perform remote creation command"""
                storage_factory = remote_connection.get_connection('storage_factory')
                storage_factory.create(name=name, storage_type=storage_type,
                                       location=location, shared=shared,
                                       node_config=node_config, id_=id_)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_create)

        return self.get_object(id_)

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses"""
        # Set permissions as having been checked, as listing VMs
        # does not require permissions
        self._get_registered_object('auth').set_permission_asserted()

        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Name', 'Type', 'Location', 'Nodes', 'Shared', 'Free Space'))

        # Set column alignment and widths
        table.set_cols_width((15, 5, 30, 70, 6, 9))
        table.set_cols_align(('l', 'l', 'l', 'l', 'l', 'l'))

        for storage_backend in self.get_all():
            table.add_row((
                storage_backend.name,
                storage_backend.storage_type,
                storage_backend.get_location(),
                ', '.join(storage_backend.nodes),
                str(storage_backend.shared),
                convert_size_friendly(storage_backend.get_free_space())
            ))
        return table.draw()

    @Expose()
    def node_pre_check(self, location, storage_type):
        """Ensure node is suitable for storage backend"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)
        cluster = self._get_registered_object('cluster')
        libvirt_config = self._get_registered_object('libvirt_config')
        self.get_class(storage_type).node_pre_check(cluster=cluster,
                                                    libvirt_config=libvirt_config,
                                                    location=location)

    def get_config(self):
        """Return the configs for storage backends"""
        return MCVirtConfig().get_config()[Factory.STORAGE_CONFIG_KEY]

    def get_id_by_name(self, name):
        """Determine the ID of a storage backend by name"""
        config = self.get_config()

        # Check each
        for id_ in config:
            if config[id_]['name'] == name:
                return id_

        # Return False if it does not exist
        return False

    def check_exists(self, id_):
        """Determine if a storage backend exists by ID"""
        return id_ in self.get_config().keys()

    @Expose()
    def get_object(self, id_):
        """Return a storage backend object"""
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
            self._register_object(storage_object)
            Factory.CACHED_OBJECTS[id_] = storage_object

        return Factory.CACHED_OBJECTS[id_]

    @Expose()
    def get_object_by_name(self, name):
        """Return a storage object by name"""
        object_id = self.get_id_by_name(name)
        if not object_id:
            raise StorageBackendDoesNotExist('Storage backend does not exist: %s' % name)
        return self.get_object(object_id)

    def get_storage_types(self):
        """Return the available storage types that MCVirt provides"""
        return get_all_submodules(Base)

    def get_class(self, storage_type):
        """Obtain the storage class for a given storage type"""
        for storage_class in self.get_storage_types():
            if storage_type == storage_class.__name__:
                return storage_class
        raise UnknownStorageTypeException(
            'Attempted to initialise an unknown storage type: %s' %
            (storage_type)
        )

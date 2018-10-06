"""Provide base operations to manage storage backends"""

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
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.utils import get_hostname
from mcvirt.exceptions import (UnsuitableNodeException,
                               NodeAlreadyConfiguredInStorageBackend,
                               StorageBackendInUse,
                               StorageBackendNotAvailableOnNode,
                               InvalidStorageConfiguration,
                               VolumeDoesNotExistError,
                               VolumeIsNotActiveException,
                               NoConfigurationChangeError,
                               CannotUnshareInUseStorageBackendError,
                               NodeUsedByStaticVirtualMachine,
                               NodeNotConfiguredInStorageBackend,
                               CannotRemoveNodeFromGlobalStorageBackend)
from mcvirt.system import System


class Base(PyroObject):
    """Provides base functionality for storage backends"""

    @classmethod
    def check_permissions(cls, libvirt_config, directory):
        """Method to check permissions of directory"""
        raise NotImplementedError

    @staticmethod
    def validate_config(cluster, config):
        """Validate config"""
        # Ensure that all nodes specified are valid
        for node in config['nodes']:
            cluster.ensure_node_exists(node, include_local=True)

    @classmethod
    def node_pre_check(cls, cluster, libvirt_config, location):
        """Ensure volume group exists on node"""
        try:
            cls.ensure_exists(location)
        except InvalidStorageConfiguration, exc:
            raise InvalidStorageConfiguration(
                '%s on node %s' % (str(exc), get_hostname())
            )
        cls.check_permissions(libvirt_config, location)

    @classmethod
    def validate_location_name(cls, location):
        """Validate location for staorage backend"""
        raise NotImplementedError

    @classmethod
    def ensure_exists(cls, location):
        """Ensure that the underlying storage exists"""
        raise NotImplementedError

    @classmethod
    def check_exists_local(cls, location):
        """Determine if underlying storage actually exists on the node.
        A static method, called by member method check_exists
        """
        raise NotImplementedError

    def __init__(self, name):
        """Setup member variables"""
        self._name = name

    def __eq__(self, comp):
        """Allow for comparison of storage objects baesd on name"""
        # Ensure class and name of object match
        if ('__class__' in dir(comp) and
                comp.__class__ == self.__class__ and
                'name' in dir(comp) and comp.name == self.name):
            return True

        # Otherwise return false
        return False

    @property
    def _volume_class(self):
        """Return the volume class for the storage backend"""
        return BaseVolume

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

    @property
    def is_global(self):
        """Determine if storage backend is global"""
        # Currently, none of the storage backends are global
        # @TODO Implement once global feature is present
        return False

    @Expose(locking=True)
    def delete(self):
        """Shared function to remove storage"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        # Determine if storage backend if used by VMs
        if self.in_use():
            raise StorageBackendInUse('Storage backend cannot be removed as it is used by VMs')

        # Remove VM from MCVirt configuration
        def update_mcvirt_config(config):
            """Remove object from mcvirt config"""
            del config['storage_backends'][self.name]
        MCVirtConfig().update_config(
            update_mcvirt_config,
            'Removed storage backend \'%s\' from global MCVirt config' %
            self.name
        )

        # Remove from remote machines in cluster
        if self._is_cluster_master:
            def remote_command(remote_object):
                """Delete backend storage from remote nodes"""
                remote_storage_backend = self.get_remote_object(node_object=remote_object)
                remote_storage_backend.delete()
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

        # Remove cached pyro object
        storage_factory = self._get_registered_object('storage_factory')
        if self.name in storage_factory.CACHED_OBJECTS:
            self.unregister_object()
            del storage_factory.CACHED_OBJECTS[self.name]

    @Expose()
    def get_config(self):
        """Get config for storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        return self._get_registered_object('storage_factory').get_config()[self.name]

    @Expose(locking=True)
    def set_location(self, new_location, node=None):
        """Set a new location for storage backend.
        None will mean no default location
        If node is set to None, the default location will be set
        """
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)
        # @TODO Add error checking - does it exist?

        def update_location_config(config):
            """Update location in config"""
            if node is None:
                config['location'] = new_location
            else:
                config['nodes'][node]['location'] = new_location
        self.update_config(update_location_config,
                           'Update location for %s' % self.name)

        if self._is_cluster_master:
            def update_remote_node(conn):
                """Update location on remote nodes"""
                remote_storage_backend = self.get_remote_object(node_object=conn)
                remote_storage_backend.set_location(new_location=new_location,
                                                    node=node)
            self._get_registered_object('cluster').run_remote_command(update_remote_node)

    @Expose(locking=True)
    def add_node(self, node_name, custom_location=None):
        """Add a new node to the storage backend"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        location = custom_location if custom_location else self.get_location(return_default=True)

        if location is None:
            raise InvalidStorageConfiguration(
                'Storage backend has no global location, so must be specified')

        # Ensure node is not already attached to storage backend
        if node_name in self.nodes:
            raise NodeAlreadyConfiguredInStorageBackend(
                'Node already configured in storage backend: %s %s' % node_name, self.name
            )

        cluster = self._get_registered_object('cluster')

        # If adding local node to cluster
        if self._is_cluster_master:
            if node_name == get_hostname():

                # Ensure that the requested volume exists
                storage_factory = self._get_registered_object('storage_factory')
                storage_factory.node_pre_check(storage_type=self.storage_type,
                                               location=location)
            else:
                def pre_check_remote(connection):
                    """Perform pre check on remote node"""
                    remote_storage_factory = connection.get_connection('storage_factory')
                    remote_storage_factory.node_pre_check(storage_type=self.storage_type,
                                                          location=location)
                cluster.run_remote_command(pre_check_remote, node=node_name)

        def update_storage_backend_config(config):
            """Add node to storage backend config"""
            config['nodes'][node_name] = {
                'location': custom_location
            }
        # Update the config on the local node
        self.update_config(
            update_storage_backend_config,
            'Add node %s to storage backend %s' % (node_name, self.name))

        if self._is_cluster_master:
            # Perform this function on remote nodes
            def update_remote_mcvirt_config(connection):
                """Update MCVirt config on remote node"""
                remote_storage_backend = self.get_remote_object(node_object=connection)
                remote_storage_backend.add_node(node_name=node_name,
                                                custom_location=custom_location)

            cluster.run_remote_command(update_remote_mcvirt_config)

    def update_config(self, callback, reason):
        """Update backend storage configuration"""
        def update_mcvirt_config(config):
            """Update MCVirt config by calling callback method"""
            callback(
                config[
                    self._get_registered_object('storage_factory').STORAGE_CONFIG_KEY
                ][self.name]
            )
        mcvirt_config = self._get_registered_object('mcvirt_config')()
        mcvirt_config.update_config(update_mcvirt_config, reason)

    def is_static(self):
        """Determine if the storage backend implies that
        nodes are static"""
        return not self.shared

    def ensure_can_remove_node(self, node_name):
        """Ensure that a node can be removed from a storage backend"""
        # Ensure that node is already part of storage backend
        if self.available_on_node(node_name, raise_on_err=True):
            raise NodeNotConfiguredInStorageBackend(
                'Node is not configured for storage backend')

        # Ensure that node has no VMs registered on the node that use this storage backend
        if self.in_use(node_name):
            raise StorageBackendInUse(
                'Virtual machine registered on the node require this storage backend')

        # Ensure that there are no virtual machines that:
        #  - Have static availalble nodes
        #  - Use this storage backend; and
        #  - This node is one of the available nodes
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for virtual_machine in virtual_machine_factory.getAllVirtualMachines():
            used_storage_backends = [hdd.get_storage_backend()
                                     for hdd in virtual_machine.getHardDriveObjects()]
            if (self in used_storage_backends and virtual_machine.is_static() and
                    node_name in virtual_machine.getAvailableNodes()):
                raise NodeUsedByStaticVirtualMachine(
                    'Storage backend on node is used by static virtual machines')

    @Expose(locking=True)
    def remove_node(self, node_name):
        """Remove a node from the storage backend"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        # Perform checks on cluster master
        if self._is_cluster_master:
            self.ensure_can_remove_node(node_name)

        # Assuming that these checks have passed,
        # remove node from storage backend
        def update_config(config):
            """Update the storage backend config; removing the node"""
            del config['nodes'][node_name]
        self.update_config(update_config,
                           'Remove node %s from storage backend %s' % (node_name, self.name))

        # Perform on remote nodes
        if self._is_cluster_master:
            def remove_node_remote(connection):
                """Update shared status of remote nodes"""
                remote_storage_backend = self.get_remote_object(node_object=connection)
                remote_storage_backend.remove_node(node_name)
            self._get_registered_object('cluster').run_remote_command(
                remove_node_remote)

    @Expose(locking=True)
    def set_shared(self, shared):
        """Set the shared status of the storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_BACKEND)

        ArgumentValidator.validate_boolean(shared)

        # Check if there's no change to configuration
        if self.shared == shared:
            raise NoConfigurationChangeError('Storage backend is already set to %s' % str(shared))

        if self.shared and self.in_use():
            raise CannotUnshareInUseStorageBackendError(
                'Storage backend is in use, so cannot unshare')

        def update_shared_config(config):
            """Set sared parameter to new value"""
            config['shared'] = shared
        self.update_config(update_shared_config, 'Update shared status to %s' % shared)

        if self._is_cluster_master:
            def update_shared_remote_nodes(connection):
                """Update shared status of remote nodes"""
                remote_storage_backend = self.get_remote_object(node_object=connection)
                remote_storage_backend.set_shared(shared)
            self._get_registered_object('cluster').run_remote_command(
                update_shared_remote_nodes)

    def in_use(self, node=None):
        """Whether the storage backend is used for any disks objects"""
        # Get VM factory
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')

        # Iterate over all virtual machine and hard drive objects
        for virtual_machine in virtual_machine_factory.getAllVirtualMachines(node=node):
            for hard_drive in virtual_machine.getHardDriveObjects():

                # If the hard drive object uses the current storage backend,
                # return True
                if hard_drive.get_storage_backend() == self:
                    return True

        # If no matches have been found, return False
        return False

    def get_location(self, node=None, return_default=False):
        """Return the location for a given node, default to local node"""
        # Default node to local node
        if node is None:
            node = get_hostname()

        # Raise exception if node is not configured for storage backend
        if node not in self.nodes:
            raise UnsuitableNodeException(
                'Node does not support storage backend: %s, %s' % (node, self.name)
            )
        config = self.get_config()
        return (config['nodes'][node]['location']
                if 'location' in config['nodes'][node] and
                config['nodes'][node]['location'] and
                not return_default
                else config['location'])

    def available_on_node(self, node=None, raise_on_err=True):
        """Determine if the storage volume is available on
        a given node
        """
        if node is None:
            node = get_hostname()

        available = (node in self.nodes)
        if not available and raise_on_err:
            raise StorageBackendNotAvailableOnNode(
                'Storage not available on node: %s, %s' % (self.name, node)
            )
        return available

    @Expose()
    def get_volume(self, name):
        """Return a volume for the current storage volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        # Create volume object
        volume = self._volume_class(name=name, storage_backend=self)
        # Register with daemon
        self._register_object(volume)
        return volume

    def is_drbd_suitable(self):
        """Return boolean depending on whether storage backend is suitable to be
        used for backing DRBD
        """
        return not self.shared

    def check_exists(self):
        """Check volume groups exists on the local node"""
        return self.__class__.check_exists_local(self.get_location())

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the current storage backend object on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_storage_factory = node_object.get_connection('storage_factory')
        remote_storage = remote_storage_factory.get_object(self.name)
        node_object.annotate_object(remote_storage)
        return remote_storage

    @Expose(remote_nodes=True)
    def get_free_space(self):
        """Return the amount of free spacae in the storage backend"""
        raise NotImplementedError


class BaseVolume(PyroObject):
    """Base class for handling volume actions.
    These classes do NOT care about a virtual machine,
    only about performing necessary commands to manipulate a
    disk on the system
    """

    def __init__(self, name, storage_backend):
        """Setup vairables"""
        self._name = name
        self._validate_name()
        self._storage_backend = storage_backend

    @property
    def name(self):
        """Return the name of the volume"""
        return self._name

    @property
    def storage_backend(self):
        """Return the storage backend"""
        return self._storage_backend

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the current volume object on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None and node is not None:
            node_object = cluster.get_remote_node(node)

        # Obtian remote storage backend
        remote_storage = self.storage_backend.get_remote_object(
            node_object=node_object
        )

        # Obtian remote volume and annotate
        remote_volume = remote_storage.get_volume(self.name)
        node_object.annotate_object(remote_volume)

        # Return remote_volume
        return remote_volume

    def ensure_exists(self):
        """Ensure that the volume exists"""
        if not self.check_exists():
            raise VolumeDoesNotExistError('Volume (%s) does not exist' % self.name)

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def wipe(self, _f=None):
        """Wipe the volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        System.perform_dd(source=System.WIPE,
                          destination=self.get_path(),
                          size=self.get_size())

    def get_sectors(self):
        """Get number of sectors allocated to the volume"""
        # Obtain size of raw volume
        _, raw_size_sectors, _ = System.runCommand(['blockdev', '--getsz', self.get_path()])
        return int(raw_size_sectors.strip())

    def get_sector_size(self):
        """Get sector size for volume"""
        # Obtain size of sectors
        _, sector_size, _ = System.runCommand(['blockdev', '--getss', self.get_path()])
        return int(sector_size.strip())

    def _validate_name(self):
        """Ensurue name of object is valid"""
        raise NotImplementedError

    def get_path(self, node=None):
        """Get the path of the volume"""
        raise NotImplementedError

    def clone(self, destination_volume):
        """Clone a volume to a new volume"""
        raise NotImplementedError

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def create(self, size, _f=None):
        """Create volume in storage backend"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        raise NotImplementedError

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def delete(self, ignore_non_existent, _f=None):
        """Delete volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        raise NotImplementedError

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def activate(self, _f=None):
        """Activate volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        raise NotImplementedError

    def is_active(self):
        """Return whether volume is activated"""
        raise NotImplementedError

    def ensure_active(self):
        """Ensure that voljuem is active, otherwise, raise exception"""
        if not self.is_active():
            raise VolumeIsNotActiveException(
                'Volume %s is not active on %s' %
                (self.name, get_hostname())
            )

    def snapshot(self, destination_volume, size):
        """Snapshot volume"""
        raise NotImplementedError

    def deactivate(self):
        """Deactivate volume"""
        raise NotImplementedError

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def resize(self, size, increase, _f=None):
        """Reszie volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        raise NotImplementedError

    def check_exists(self):
        """Determine whether volume exists"""
        raise NotImplementedError

    @Expose(remote_nodes=True)
    def get_size(self):
        """Obtain the size of the volume"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        raise NotImplementedError

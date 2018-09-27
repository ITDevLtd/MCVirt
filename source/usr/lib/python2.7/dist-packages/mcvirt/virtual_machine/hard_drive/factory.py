# Copyright (c) 2014 - I.T. Dev Ltd
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

"""
#########################################################################################
##################################   STORAGE  LAYOUT   ##################################
#########################################################################################
#
#        ------------
#       | Hard drive | Provides an interface for libvirt
#    ---|    Base    | configuration, high level 'creation', 'deletion'
#    |   ------------  function. Handling pre/post migration tasks and
#    |        |        determining capabilities of hard drive.
#    |        |        This class does not interact with the OS to modify
#    |        |        actual storage (with the exception of DRBD commands).
#    |        |        This class performs all non-OS-level-storage checking
#    |        |        before actions are performed, e.g. ensure VM is powered
#    |        |        off and checking user permissions.
#    |        |        The object can be created before volume exists on disk.
#    |        |
#    |        |--- Local
#    |        |      - Local hard drive object provides
#    |        |        an interface for a single-volume backed storage.
#    |        |        This could be used for either be a single-node VM or
#    |        |        on shared storage
#    |        |
#    |        |
#    |        |
#    |         --- Drbd
#    |               - DRBD object provides additional overlay for managing
#    |                 the multiple backend volumes, that's required by DRBD,
#    |                 an alternative front-end block devide (drbd volume),
#    |                 as well as montioring of the DRBD volume. This must
#    |                 use local storage, as the volume is replicatated
#    |                 to other nodes via DRBD. All DRBD commands are executed
#    |                 from this class
#    |
#    |      --------
#     ---> | Volume |  Given the storage backend (as supplied by the disk object
#       -> |  Base  |  when creating the volume object), this class provides
#      |    --------   and interface to interact with the OS to create/modify
#      |       |       the underlying storage volumes. All 'create', 'delete' etc.,
#      |       |       commands in the hard drive objects call to the respective
#      |       |       volume objects to make the system modification. This object
#      |       |       has no concept of a virtual machine, it performs disks commands,
#      |       |       given the disk name and storage backend.
#      |       |       The object can be created before the volume exists on disk.
#.     |       |
#      |       |--- LVM
#      |       |       This performs OS commands to manage a given logival-volume-based
#      |       |       disk, where the underlying storage backend is LVM-based.
#      |       |
#      |        --- File
#      |               This performs OS commands to manage a given file-based disk,
#      |               where the underlying storage backend is Directory-based.
#      |
#      |     -----------
#       ----|  Storage  | Provides an interface for managing/differentiating different
#           | (Backend) | sets/types of physical storage. When this object is created,
#           |    Base   | the backing storage must be present on the requested nodes.
#            -----------  This object is used to determine which nodes the storage is
#               |         available to and contribute to which nodes a VM will be
#               |         compatible with.
#               |
#               |------- LVM
#               |      Allows for addition of LVM volume-group based storage.
#               |      When a disk object is created, using this as a storage backend,
#               |      an LVM-based volume is returned for OS-calls.
#               |
#                ------- File
#                      Allows for addition of directory based storage.
#                      When a disk object is created, using this as a storage backend,
#                      an File volume is returned for OS-calls.
#
#########################################################################################
#########################################################################################
"""

import Pyro4

from mcvirt.exceptions import (UnknownStorageTypeException, HardDriveDoesNotExistException,
                               InsufficientSpaceException, StorageBackendNotAvailableOnNode,
                               UnknownStorageBackendException, InvalidNodesException)
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import Drbd
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname
from mcvirt.rpc.expose_method import Expose


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects"""

    STORAGE_TYPES = [Local, Drbd]
    DEFAULT_STORAGE_TYPE = 'Local'
    OBJECT_TYPE = 'hard disk'
    HARD_DRIVE_CLASS = Base
    CACHED_OBJECTS = {}

    @Expose()
    def getObject(self, vm_object, disk_id, **config):
        """Returns the storage object for a given disk"""
        vm_object = self._convert_remote_object(vm_object)

        # Obtain VM config and initialise storage type value
        vm_config = vm_object.get_config_object().get_config()
        storage_type = None

        # Default to storage type in vm config, if defined
        if vm_config['storage_type']:
            storage_type = vm_config['storage_type']

        # If the storage type as been overriden in the VM config,
        # use this and remove from overrides
        if 'storage_type' in config:
            if storage_type is None:
                storage_type = config['storage_type']
            del config['storage_type']

        # Create cache key, based on name of VM, disk ID and storage type
        storage_type_key = storage_type or ''
        cache_key = (vm_object.get_name(), disk_id, storage_type_key)

        # If configuring overrides have been used, do not cache the object.
        disable_cache = (len(config))

        # If cache is disabled, remove object from cache and return the object directly.
        # Otherwise, if object is not in object cache, create it.
        if disable_cache:
            if cache_key in Factory.CACHED_OBJECTS:
                del Factory.CACHED_OBJECTS[cache_key]
        if cache_key not in Factory.CACHED_OBJECTS:
            hard_drive_object = self.getClass(storage_type)(
                vm_object=vm_object, disk_id=disk_id, **config)
            self._register_object(hard_drive_object)
            if disable_cache:
                return hard_drive_object
            Factory.CACHED_OBJECTS[cache_key] = hard_drive_object

        # If cache is not disabled, return the cached object
        return Factory.CACHED_OBJECTS[cache_key]

    @Expose()
    def ensure_hdd_valid(self, size, storage_type, nodes, storage_backend, nodes_predefined=False):
        """Ensures the HDD can be created on all nodes, and returns the storage type to be used."""

        storage_type_predefined = sotrage_type is not None
        storage_backend_predefined = storage_backend is not None

        # Ensure that, if storage type is specified, that it's in the list of available storage
        # backends for this node.
        # @TODO IF a storage type has been specified, which does not support DBRD, then
        # we can assume that Local storage is used.
        hard_drive_factory = self._get_registered_object('hard_drive_factory')
        available_storage_types = hard_drive_factory._get_available_storage_types()
        if storage_type:
            if (storage_type not in
                    [available_storage.__name__ for available_storage in available_storage_types]):
                raise UnknownStorageTypeException('%s is not supported by node %s' %
                                                  (storage_type, get_hostname()))
        else:
            # Otherwise, if no storage type has been defined, ensure that there is only
            # 1 avilable storage type.
            if len(available_storage_types) > 1:
                raise UnknownStorageTypeException('Storage type must be specified')
            elif len(available_storage_types) == 1:
                storage_type = available_storage_types[0].__name__
            else:
                raise UnknownStorageTypeException('There are no storage types available')

        # Before any further calculations are performed, if DRBD has been selected
        # and there are more or fewer than 2 available nodes with DRBD enabled,
        # the user MUST determine which two nodes will be used.
        if storage_type == Drbd.__name__:
            node_drbd = self._get_registered_object('node_drbd')
            for node in nodes:
                # If DRBD is not enabled on the node, remove it from the list
                # of nodes
                if not node_drbd.is_enabled(node=node):
                    nodes.delete(node)

            # If number of nodes is less than or greater than 2, raise exceptions, as
            # DRBD requires exactly 2 nodes
            if len(nodes) != node_drbd.CLUSTER_SIZE:
                raise InvalidNodesException('Exactly %i nodes must be specified for DRBD'
                                            % node_drbd.CLUSTER_SIZE)

        # If storage backend has been defined, ensure it is available on the current node
        storage_backend_nodes = list(nodes)
        if storage_backend:
            for node in nodes:
                if nodes_predefined:
                    storage_backend.available_on_node(node=node, raise_on_err=True)
                elif storage_backend.available_on_node(node=node, raise_on_err=False):
                    storage_backend_nodes.remove(node)

        # Otherwise, if storage backend has not been defined, ensure that
        # there is only one available for the given storage type and nodes selected
        else:
            storage_factory = self._get_registered_object('storage_factory')
            available_storage_backends = storage_factory.get_all(
                nodes=nodes, drbd=(storage_type == Drbd.__name__),
                nodes_predefined=nodes_predefined
            )
            if len(available_storage_backends) > 1:
                raise UnknownStorageBackendException('Storage backend must be specified')
            elif len(available_storage_backends) == 1:
                storage_backend = available_storage_backends[0]
                storage_backend_nodes = storage_backend.nodes

                # Remove any nodes from the list of nodes that aren't
                # available to the node
                for node in storage_backend.nodes:
                    if node not in nodes:
                        nodes.remove(node)
            else:
                raise UnknownStorageBackendException('There are no available storage backends')

        free = storage_backend.get_free_space()
        if free < size:
            raise InsufficientSpaceException('Attempted to create a disk with %i MB, but there '
                                             'is only %i MB of free space available in storage '
                                             'backend \'%s\' on node %s.' %
                                             (size, free, storage_backend.name, get_hostname()))

        return nodes, storage_type, storage_backend

    @Expose(locking=True)
    def create(self, vm_object, size, storage_type, driver, storage_backend=None):
        """Performs the creation of a hard drive, using a given storage type"""
        vm_object = self._convert_remote_object(vm_object)
        if storage_backend is not None:
            storage_backend = self._convert_remote_object(storage_backend)

        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            vm_object
        )

        nodes = vm_object.getAvailableNodes()
        storage_type, storage_backend = self.ensure_hdd_valid(size, storage_type, nodes,
                                                              storage_backend)

        # Ensure the VM storage type matches the storage type passed in
        vm_storage_type = vm_object.getStorageType()
        if vm_storage_type:
            if storage_type and storage_type != vm_storage_type:
                raise UnknownStorageTypeException(
                    ('Spcifeid storage type \'%s\' does not match '
                     'VM\'s current storage type: %s') % (storage_type, vm_storage_type)
                )

        hdd_object = self.getClass(storage_type)(vm_object=vm_object, driver=driver,
                                                 storage_backend=storage_backend)
        self._register_object(hdd_object)
        hdd_object.create(size=size)
        return hdd_object

    def _getAvailableStorageTypes(self):
        """Returns a list of storage types that are available on the node"""
        available_storage_types = []
        storage_factory = self._get_registered_object('storage_factory')
        node_drbd = self._get_registered_object('node_drbd')
        for storage_type in self.STORAGE_TYPES:
            if storage_type.isAvailable(storage_factory, node_drbd):
                available_storage_types.append(storage_type)
        return available_storage_types

    def getStorageTypes(self):
        """Returns the available storage types that MCVirt provides"""
        return self.STORAGE_TYPES

    def getClass(self, storage_type):
        """Obtains the hard drive class for a given storage type"""
        for hard_drive_class in self.getStorageTypes():
            if (storage_type == hard_drive_class.__name__):
                return hard_drive_class
        raise UnknownStorageTypeException(
            'Attempted to initialise an unknown storage type: %s' %
            (storage_type)
        )

    @Expose()
    def getDrbdObjectByResourceName(self, resource_name):
        """Obtains a hard drive object for a Drbd drive, based on the resource name"""
        node_drbd = self._get_registered_object('node_drbd')
        for hard_drive_object in node_drbd.get_all_drbd_hard_drive_object():
            if hard_drive_object.resource_name == resource_name:
                return hard_drive_object
        raise HardDriveDoesNotExistException(
            'Drbd hard drive with resource name \'%s\' does not exist' %
            resource_name
        )

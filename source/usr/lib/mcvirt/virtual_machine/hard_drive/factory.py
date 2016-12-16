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

import Pyro4

from mcvirt.exceptions import (UnknownStorageTypeException, HardDriveDoesNotExistException,
                               InsufficientSpaceException)
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import Drbd
from mcvirt.virtual_machine.hard_drive.file import File
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname
from mcvirt.rpc.expose_method import Expose


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects"""

    STORAGE_TYPES = [Local, Drbd, File]
    DEFAULT_STORAGE_TYPE = 'Local'
    OBJECT_TYPE = 'hard disk'
    HARD_DRIVE_CLASS = Base
    CACHED_OBJECTS = {}

    @Expose()
    def getObject(self, vm_object, disk_id, **config):
        """Returns the storage object for a given disk"""
        vm_object = self._convert_remote_object(vm_object)
        vm_config = vm_object.get_config_object().get_config()
        storage_type = None
        if vm_config['storage_type']:
            storage_type = vm_config['storage_type']

        if 'storage_type' in config:
            if storage_type is None:
                storage_type = config['storage_type']
            del(config['storage_type'])
        storage_type_key = storage_type or ''
        cache_key = (vm_object.get_name(), disk_id, storage_type_key)
        if cache_key not in Factory.CACHED_OBJECTS:
            hard_drive_object = self.getClass(storage_type)(
                vm_object=vm_object, disk_id=disk_id, **config)
            self._register_object(hard_drive_object)
            Factory.CACHED_OBJECTS[cache_key] = hard_drive_object

        return Factory.CACHED_OBJECTS[cache_key]

    @Expose()
    def ensure_hdd_valid(self, size, storage_type, remote_nodes):
        """Ensures the HDD can be created on all nodes, and returns the storage type to be used."""
        available_storage_types = self._getAvailableStorageTypes()
        if storage_type:
            if (storage_type not in
                    [available_storage.__name__ for available_storage in available_storage_types]):
                raise UnknownStorageTypeException('%s is not supported by node %s' %
                                                  (storage_type, get_hostname()))
        else:
            if len(available_storage_types) > 1:
                raise UnknownStorageTypeException('Storage type must be specified')
            elif len(available_storage_types) == 1:
                storage_type = available_storage_types[0].__name__
            else:
                raise UnknownStorageTypeException('There are no storage types available')

        free = self._get_registered_object('node').get_free_vg_space()
        if free < size:
            raise InsufficientSpaceException('Attempted to create a disk with %i MiB, but there '
                                             'is only %i MiB of free space available on node %s.' %
                                             (size, free, get_hostname()))

        if self._is_cluster_master:
            def remote_command(remote_connection):
                hard_drive_factory = remote_connection.get_connection('hard_drive_factory')
                hard_drive_factory.ensure_hdd_valid(size, storage_type, remote_nodes)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(callback_method=remote_command, nodes=remote_nodes)

        return storage_type

    @Expose(locking=True)
    def create(self, vm_object, size, storage_type, driver, *args, **kwargs):
        """Performs the creation of a hard drive, using a given storage type"""
        vm_object = self._convert_remote_object(vm_object)

        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            vm_object
        )

        remote_nodes = [node for node in vm_object.getAvailableNodes() if node != get_hostname()]
        storage_type = self.ensure_hdd_valid(size, storage_type, remote_nodes)

        # Ensure the VM storage type matches the storage type passed in
        if vm_object.getStorageType():
            if storage_type and storage_type != vm_object.getStorageType():
                raise UnknownStorageTypeException(
                    'Storage type does not match VMs current storage type'
                )

        hdd_object = self.getClass(storage_type)(vm_object=vm_object, driver=driver,
                                                 *args, **kwargs)
        self._register_object(hdd_object)
        hdd_object.create(size=size)
        return hdd_object

    def _getAvailableStorageTypes(self):
        """Returns a list of storage types that are available on the node"""
        available_storage_types = []
        for storage_type in self.STORAGE_TYPES:
            if storage_type.isAvailable(self):
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

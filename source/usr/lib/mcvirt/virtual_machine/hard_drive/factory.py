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

from mcvirt.exceptions import UnknownStorageTypeException, HardDriveDoesNotExistException
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import Drbd
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.lock import locking_method
from mcvirt.rpc.pyro_object import PyroObject


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects"""

    STORAGE_TYPES = [Local, Drbd]
    DEFAULT_STORAGE_TYPE = 'Local'
    OBJECT_TYPE = 'hard disk'
    HARD_DRIVE_CLASS = Base

    @Pyro4.expose()
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

        hard_drive_object = self.getClass(storage_type)(
            vm_object=vm_object, disk_id=disk_id, **config)
        self._register_object(hard_drive_object)

        return hard_drive_object

    @Pyro4.expose()
    @locking_method()
    def create(self, vm_object, size, storage_type, driver):
        """Performs the creation of a hard drive, using a given storage type"""
        vm_object = self._convert_remote_object(vm_object)

        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            vm_object
        )

        # Ensure that the storage type:
        # If the VM's storage type has been defined that the specified storage type
        #   matches or has not been defined.
        # Or that the storage type has been specified if the VM's storage type is
        #   not defined
        if vm_object.getStorageType():
            if storage_type and storage_type != vm_object.getStorageType():
                raise UnknownStorageTypeException(
                    'Storage type does not match VMs current storage type'
                )
            storage_type = vm_object.getStorageType()

        available_storage_types = self._getAvailableStorageTypes()
        if storage_type:
            if (storage_type not in
                    [available_storage.__name__ for available_storage in available_storage_types]):
                raise UnknownStorageTypeException('%s is not supported by this node' %
                                                  storage_type)
        else:
            if len(available_storage_types) > 1:
                raise UnknownStorageTypeException('Storage type must be specified')
            elif len(available_storage_types) == 1:
                storage_type = available_storage_types[0].__name__
            else:
                raise UnknownStorageTypeException('There are no storage types available')
        hdd_object = self.getClass(storage_type)(vm_object=vm_object, driver=driver)
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

    @Pyro4.expose()
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

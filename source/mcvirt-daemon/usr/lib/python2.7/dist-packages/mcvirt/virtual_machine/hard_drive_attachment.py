# Copyright (c) 2018 - Matt Comben
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

import xml.etree.ElementTree as ET

from mcvirt.exceptions import (ReachedMaximumStorageDevicesException,
                               StorageTypesCannotBeMixedException,
                               UnknownStorageTypeException,
                               HardDriveNotAttachedToVirtualMachineError,
                               HardDriveAttachmentDoesNotExistError)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.utils import get_hostname


class Factory(PyroObject):

    CACHED_OBJECTS = {}

    def get_remote_object(self,
                          node=None,  # The name of the remote node to connect to
                          node_object=None):  # Otherwise, pass a remote node connection
        """Obtain an instance of the hard drive attachment factory on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('hard_drive_attachment_factory')

    @Expose()
    def get_object(self, virtual_machine, attachment_id):
        """Obtain hard drive attachment object."""
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        attachment_id = str(attachment_id)

        cache_id = (virtual_machine.id_, attachment_id)

        # Determine if VM object has been cached
        if cache_id not in Factory.CACHED_OBJECTS:
            # Ensure that the attachment exists
            if attachment_id not in virtual_machine.get_config_object().get_config()['hard_drives']:
                raise HardDriveAttachmentDoesNotExistError(
                    'Hard drive attachment does not exist')

            # If not, create object, register with pyro
            # and store in cached object dict
            hdd_attachment = HardDriveAttachment(virtual_machine, attachment_id)
            self.po__register_object(hdd_attachment)

            Factory.CACHED_OBJECTS[cache_id] = hdd_attachment

        # Return the cached object
        return Factory.CACHED_OBJECTS[cache_id]

    def get_objects_by_virtual_machine(self, virtual_machine):
        """Obtain attachments by virtual machine."""
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        attachment_ids = virtual_machine.get_config_object().get_config()['hard_drives'].keys()
        return [self.get_object(virtual_machine, id_) for id_ in attachment_ids]

    @Expose()
    def get_object_by_hard_drive(self, hard_drive, raise_on_failure=False):
        """Obtain attachment by hard drive."""
        hard_drive = self.po__convert_remote_object(hard_drive)

        # Iterate over each virtual machine and each attachment on the VM
        for vm in self.po__get_registered_object(
                'virtual_machine_factory').get_all_virtual_machines():
            for attachment in self.get_objects_by_virtual_machine(vm):
                # If the hard drive ID matches the ID of the hard drive
                # being searched for, return the attachment
                if attachment.get_hard_drive_object() == hard_drive:
                    return attachment

        if raise_on_failure:
            raise HardDriveNotAttachedToVirtualMachineError(
                'Hard drive not attached to virtual machine')
        return None

    @Expose(locking=True)
    def create(self, virtual_machine, hard_drive):
        """Create attachment."""
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        hard_drive = self.po__convert_remote_object(hard_drive)

        # Ensure that the user has permissions to modify VM
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            virtual_machine
        )

        attachment_id = self._get_available_attachment_id(virtual_machine)

        # Ensure that the new disk matches the same 'shared' and 'storage' type as the
        # new disk
        for vm_hdd in virtual_machine.get_hard_drive_objects():
            hard_drive.ensure_compatible(vm_hdd)

        config = {
            'hard_drive_id': hard_drive.id_
        }

        cluster = self.po__get_registered_object('cluster')
        self.create_config(
            virtual_machine=virtual_machine, attachment_id=attachment_id,
            config=config,
            nodes=cluster.get_nodes(include_local=True))

        attachment_object = self.get_object(virtual_machine, attachment_id)
        attachment_object.add_to_virtual_machine()

        return attachment_object

    @Expose(locking=True, remote_nodes=True)
    def create_config(self, virtual_machine, attachment_id, config):
        """Add hard drive attachment config to VM."""
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        attachment_id = str(attachment_id)

        # Ensure that the user has permissions to modify VM
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            virtual_machine
        )

        def add_attachment_config(vm_config):
            """Add attachment config to VM config."""
            vm_config['hard_drives'][str(attachment_id)] = config

        virtual_machine.get_config_object().update_config(
            add_attachment_config,
            'Add hard drive attachment for %s' % virtual_machine.get_name())

    def _get_available_attachment_id(self, virtual_machine):
        """Obtain the next available ID for the VM hard drive, by scanning the IDs
        of disks attached to the VM
        """
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        attachment_id = 0
        disks = virtual_machine.get_config_object().get_config()['hard_drives'].keys()
        hdd_class = self.po__get_registered_object('hard_drive_factory').get_class(
            virtual_machine.get_storage_type(), allow_base=True)

        # Ensure that the number of disks attached to the VM is not already
        # at the maximum
        if len(disks) >= hdd_class.MAXIMUM_DEVICES:
            raise ReachedMaximumStorageDevicesException(
                'A maximum of %s hard drives of this type can be mapped to a VM' %
                hdd_class.MAXIMUM_DEVICES)

        # Increment disk ID until a free ID is found
        while True:
            attachment_id += 1
            if not str(attachment_id) in disks:
                return attachment_id


class HardDriveAttachment(PyroObject):
    """Defines a link between a hard drive and a virtual machine."""

    def __init__(self, virtual_machine, attachment_id):
        """Initialise member variables."""
        self.virtual_machine = virtual_machine
        self.attachment_id = attachment_id
        self.hard_drive_id = None

    def get_remote_object(self,
                          node=None,  # The name of the remote node to connect to
                          node_object=None):  # Otherwise, pass a remote node connection
        """Obtain an instance of the hard drive attachment factory on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_virtual_machine_factory = node_object.get_connection('virtual_machine_factory')
        remote_virtual_machine = remote_virtual_machine_factory.get_virtual_machine_by_id(
            self.virtual_machine.id_)
        node_object.annotate_object(remote_virtual_machine)

        remote_hdd_attachment = node_object.get_connection(
            'hard_drive_attachment_factory').get_object(
                remote_virtual_machine, self.attachment_id)

        node_object.annotate_object(remote_hdd_attachment)

        return remote_hdd_attachment

    @property
    def _target_dev(self):
        """Determine the target dev, based on the disk's ID."""
        # Use ascii numbers to map 1 => a, 2 => b, etc...
        return 'sd' + chr(96 + int(self.attachment_id))

    def get_config(self):
        """Get hard drive attachment config."""
        vm_config = self.virtual_machine.get_config_object().get_config()
        return vm_config['hard_drives'][self.attachment_id]

    def get_hard_drive_id(self):
        """Obtain the hard rive ID."""
        if self.hard_drive_id is None:
            self.hard_drive_id = self.get_config()['hard_drive_id']

        return self.hard_drive_id

    @Expose()
    def get_hard_drive_object(self):
        """Get hard drive object."""
        hdd_factory = self.po__get_registered_object('hard_drive_factory')
        return hdd_factory.get_object(self.get_hard_drive_id())

    @Expose(locking=True)
    def delete(self, local_only=False):
        """Remove the hard drive attachment."""
        # Ensure that the user has permissions to add delete storage
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.virtual_machine
        )

        self.remove_from_virtual_machine()
        cluster = self.po__get_registered_object('cluster')
        nodes = [get_hostname()] if local_only else cluster.get_nodes(include_local=True)
        self.remove_config(nodes=cluster.get_nodes(include_local=True))
        del Factory.CACHED_OBJECTS[(self.virtual_machine.id_, self.attachment_id)]
        self.po__unregister_object()

    @Expose(locking=True, remote_nodes=True)
    def remove_config(self):
        """Remove the config from the virtual machine."""

        def update_vm_config(vm_config):
            """Remove attachment config from VM."""
            del vm_config['hard_drives'][str(self.attachment_id)]

        self.virtual_machine.get_config_object().update_config(
            update_vm_config,
            'Remove disk attachment from VM')

    def generate_libvirt_xml(self):
        """Create a basic libvirt XML configuration for the connection to the disk."""
        hdd_object = self.get_hard_drive_object()

        # Create the base disk XML element
        device_xml = ET.Element('disk')
        device_xml.set('type', hdd_object.libvirt_device_type)
        device_xml.set('device', 'disk')

        # Configure the interface driver to the disk
        driver_xml = ET.SubElement(device_xml, 'driver')
        driver_xml.set('name', 'qemu')
        driver_xml.set('type', 'raw')
        driver_xml.set('cache', hdd_object.CACHE_MODE)

        # Configure the source of the disk
        source_xml = ET.SubElement(device_xml, 'source')
        source_xml.set(hdd_object.libvirt_source_parameter, hdd_object.getDiskPath())

        # Configure the target
        target_xml = ET.SubElement(device_xml, 'target')
        target_xml.set('dev', '%s' % self._target_dev)
        target_xml.set('bus', hdd_object.get_libvirt_driver())

        return device_xml

    @Expose(locking=True, remote_nodes=True, undo_method='remove_from_virtual_machine')
    def add_to_virtual_machine(self):
        """Add the hard drive to the virtual machine,
        and performs the base function on all nodes in the cluster
        """
        # Ensure that the user has permissions to modify VM
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.virtual_machine
        )
        # Update the libvirt domain XML configuration
        if self.virtual_machine.is_registered_locally():
            self._register_libvirt()

    @Expose(locking=True, remote_nodes=True, undo_method='add_to_virtual_machine')
    def remove_from_virtual_machine(self):
        """Remove the hard drive from a VM configuration and perform all nodes
        in the cluster
        """
        # @TODO - NEEDS REWORK NOW
        # Ensure that the user has permissions to modify VM
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.virtual_machine
        )
        # If the VM that the hard drive is attached to is registered on the local
        # node, remove the hard drive from the LibVirt configuration
        if self.virtual_machine.is_registered_locally():
            self._unregister_libvirt()

    def _unregister_libvirt(self):
        """Removes the hard drive from the LibVirt configuration for the VM."""
        # Update the libvirt domain XML configuration
        # @TODO - NEEDS REWORK NOW
        def update_libvirt(domain_xml):
            """Update libvirt config."""
            device_xml = domain_xml.find('./devices')
            disk_xml = device_xml.find(
                './disk/target[@dev="%s"]/..' %
                self._target_dev)
            device_xml.remove(disk_xml)

        # Update libvirt configuration
        self.virtual_machine.update_libvirt_config(update_libvirt)

    def _register_libvirt(self):
        """Register the hard drive with the Libvirt VM configuration."""
        def update_libvirt(domain_xml):
            """Add disk to libvirt config."""
            drive_xml = self.generate_libvirt_xml()
            device_xml = domain_xml.find('./devices')
            device_xml.append(drive_xml)

        # Update libvirt configuration
        self.virtual_machine.update_libvirt_config(update_libvirt)

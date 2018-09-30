"""Provide base operations to manage all hard drives, used by VMs"""
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

import os
import xml.etree.ElementTree as ET
from enum import Enum

from mcvirt.exceptions import (HardDriveDoesNotExistException,
                               StorageTypesCannotBeMixedException,
                               LogicalVolumeDoesNotExistException,
                               BackupSnapshotAlreadyExistsException,
                               BackupSnapshotDoesNotExistException,
                               ExternalStorageCommandErrorException,
                               MCVirtCommandException,
                               ResyncNotSupportedException,
                               LogicalVolumeIsNotActiveException,
                               VolumeDoesNotExistError,
                               VolumeAlreadyExistsError)
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import ReachedMaximumStorageDevicesException
from mcvirt.utils import get_hostname
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.constants import LockStates


class Driver(Enum):
    """Enums for specifying the hard drive driver type"""

    VIRTIO = 'virtio'
    IDE = 'ide'
    SCSI = 'scsi'
    USB = 'usb'
    SATA = 'sata'
    SD = 'sd'


class Base(PyroObject):
    """Provides base operations to manage all hard drives, used by VMs"""

    # The maximum number of storage devices for the current type
    MAXIMUM_DEVICES = 1

    # The default driver for the disk
    DEFAULT_DRIVER = Driver.IDE.name

    # Set default options for snapshotting
    SNAPSHOT_SUFFIX = '_snapshot'
    SNAPSHOT_SIZE = '500M'

    # Cache mode - must be overidden
    CACHE_MODE = None

    def __init__(self, vm_object, storage_backend=None, disk_id=None, driver=None):
        """Set member variables"""
        self._disk_id = disk_id
        self._driver = driver
        self._storage_backend = storage_backend

        self.vm_object = vm_object

        # If the disk is configured on a VM, obtain
        # the details from the VM configuration
        for key, value in self.getDiskConfig().iteritems():
            setattr(self, key, value)

    @property
    def config_properties(self):
        """Return the disk object config items"""
        return ['disk_id', 'driver', 'storage_backend']

    @property
    def storage_backend(self):
        """Return storage backend"""
        return self._storage_backend

    def __setattr__(self, name, value):
        """Override setattr to ensure that the value of
        a disk config item is written to, rather than the
        property method.
        """
        if name in self.config_properties:
            name = '_%s' % name
        return super(Base, self).__setattr__(name, value)

    @property
    def disk_id(self):
        """Return the disk ID of the current disk, generating a new one
        if there is not already one present
        """
        if self._disk_id is None:
            self._disk_id = self._get_available_id()
        return self._disk_id

    @property
    def _target_dev(self):
        """Determine the target dev, based on the disk's ID"""
        # Use ascii numbers to map 1 => a, 2 => b, etc...
        return 'sd' + chr(96 + int(self.disk_id))

    @property
    def driver(self):
        """Return the disk drive driver name"""
        if self._driver is None:
            self._driver = self.DEFAULT_DRIVER
        return self._driver

    @Expose()
    def get_vm_object(self):
        """Obtain the VM object for the resource"""
        vm_name = self.vm_object.get_name()
        return self._get_registered_object(
            'virtual_machine_factory').getVirtualMachineByName(vm_name)

    def get_remote_object(self,
                          node_name=None,     # The name of the remote node to connect to
                          remote_node=None,   # Otherwise, pass a remote node connection
                          registered=True,  # If the hard drive can be setup
                          return_node=False):
        """Obtain an instance of the current hard drive object on a remote node"""
        cluster = self._get_registered_object('cluster')
        if remote_node is None:
            remote_node = cluster.get_remote_node(node_name)

        remote_vm_factory = remote_node.get_connection('virtual_machine_factory')
        remote_vm = remote_vm_factory.getVirtualMachineByName(self.vm_object.get_name())

        remote_hard_drive_factory = remote_node.get_connection('hard_drive_factory')

        kwargs = {
            'vm_object': remote_vm,
            'disk_id': self.disk_id
        }
        if not registered:
            kwargs['storage_type'] = self.get_type()

            for config in self.config_properties:
                kwargs[config] = getattr(self, config)

            remote_storage_factory = remote_node.get_connection('storage_factory')
            remote_storage_backend = remote_storage_factory.get_object(
                self.get_storage_backend().name
            )
            kwargs['storage_backend'] = remote_storage_backend

        hard_drive_object = remote_hard_drive_factory.getObject(**kwargs)
        remote_node.annotate_object(hard_drive_object)
        if return_node:
            return hard_drive_object, remote_node
        else:
            return hard_drive_object

    def _get_available_id(self):
        """Obtain the next available ID for the VM hard drive, by scanning the IDs
        of disks attached to the VM
        """
        found_available_id = False
        disk_id = 0
        vm_config = self.vm_object.get_config_object().get_config()
        disks = vm_config['hard_disks']

        # Increment disk ID until a free ID is found
        while not found_available_id:
            disk_id += 1
            if not str(disk_id) in disks:
                found_available_id = True

        # Check that the id is less than 4, as a VM can only have a maximum of 4 disks
        if int(disk_id) > self.MAXIMUM_DEVICES:
            raise ReachedMaximumStorageDevicesException(
                'A maximum of %s hard drives can be mapped to a VM' %
                self.MAXIMUM_DEVICES)

        return disk_id

    def _ensure_exists(self):
        """Ensure the disk exists on the local node"""
        if not self._check_exists():
            raise HardDriveDoesNotExistException(
                'Disk %s for %s does not exist' %
                (self.disk_id, self.vm_object.get_name()))

    def is_static(self):
        """Determine if storage is static and VM cannot be
        migrated to any node in the cluster
        """
        # By default, this is just determined whether the storage is
        # shared or not. Shared storage will allow mean storage is available
        # to any node that supports it. Otherwise, the data is only on the node
        # that the storage was created on.
        return self.get_storage_backend().is_static()

    @Expose(locking=True)
    def resync(self, source_node=None, auto_determine=False):
        """Resync the volume"""
        raise ResyncNotSupportedException('Resync is not supported on this storage type')

    @Expose()
    def get_type(self):
        """Return the type of storage for the hard drive"""
        return self.__class__.__name__

    @Expose(locking=True)
    def delete(self):
        """Delete the logical volume for the disk"""
        # Ensure that the user has permissions to add delete storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.vm_object
        )

        self._ensure_exists()

        cache_key = (self.vm_object.get_name(), self.disk_id, self.get_type())

        self.vm_object.ensureUnlocked()
        self.vm_object.ensure_stopped()

        if self.vm_object.isRegisteredLocally():
            # Remove from LibVirt, if registered, so that libvirt doesn't
            # hold the device open when the storage is removed
            self._unregisterLibvirt()

        # Remove backing storage
        self._removeStorage()

        # Remove the hard drive from the MCVirt VM configuration
        self.removeFromVirtualMachine(unregister=False)

        # Unregister object and remove from factory cache
        hdd_factory = self._get_registered_object('hard_drive_factory')
        if cache_key in hdd_factory.CACHED_OBJECTS:
            del hdd_factory.CACHED_OBJECTS[cache_key]
        self.unregister_object()

    def duplicate(self, destination_vm_object, storage_backend=None):
        """Clone the hard drive and attach it to the new VM object"""
        self._ensure_exists()

        if not storage_backend:
            storage_backend = self.get_storage_backend()

        # Create new disk object, using the same type, size and disk_id
        new_disk_object = self.__class__(vm_object=destination_vm_object, disk_id=self.disk_id,
                                         driver=self.driver,
                                         storage_backend=storage_backend)
        # Register new disk object with pyro
        self._register_object(new_disk_object)

        # Create new disk
        new_disk_object.create(self.getSize())

        # Get path of source and new disks
        source_drbd_block_device = self._getDiskPath()
        destination_drbd_block_device = new_disk_object._getDiskPath()

        # Use dd to duplicate the old disk to the new disk
        command_args = ('dd', 'if=%s' % source_drbd_block_device,
                        'of=%s' % destination_drbd_block_device, 'bs=1M')
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            new_disk_object.delete()
            raise ExternalStorageCommandErrorException(
                "Error whilst duplicating disk logical volume:\n" + str(e)
            )

        return new_disk_object

    @Expose(locking=True)
    def addToVirtualMachine(self, register=True):
        """Add the hard drive to the virtual machine,
           and performs the base function on all nodes in the cluster"""
        # Ensure that the user has permissions to modify VM
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.vm_object
        )
        # Update the libvirt domain XML configuration
        if self.vm_object.isRegisteredLocally():
            self._registerLibvirt()

        # Update the VM storage config
        self._setVmStorageType()

        # Update VM config file
        def add_disk_to_config(vm_config):
            vm_config['hard_disks'][str(self.disk_id)] = self._getMCVirtConfig()

        self.vm_object.get_config_object().update_config(
            add_disk_to_config, 'Added disk \'%s\' to \'%s\'' %
                                (self.disk_id, self.vm_object.get_name())
        )

        # If the node cluster is initialised, update all remote node configurations
        if self._is_cluster_master:

            # Create list of nodes that the hard drive was successfully added to
            successful_nodes = []
            cluster = self._get_registered_object('cluster')
            try:
                for node in cluster.get_nodes():
                    remote_disk_object = self.get_remote_object(node, registered=False)
                    remote_disk_object.addToVirtualMachine()
                    successful_nodes.append(node)
            except Exception:
                # If the hard drive fails to be added to a node, remove it from all successful nodes
                # and remove from the local node
                for node in successful_nodes:
                    self.get_remote_object(node).removeFromVirtualMachine()

                self.removeFromVirtualMachine(unregister=register, all_nodes=False)
                raise

    @staticmethod
    def isAvailable(node, node_drbd):
        """Returns whether the storage type is available on the node"""
        raise NotImplementedError

    @Expose(locking=True)
    def removeFromVirtualMachine(self, unregister=False, all_nodes=True):
        """Remove the hard drive from a VM configuration and perform all nodes
           in the cluster"""
        # Ensure that the user has permissions to modify VM
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.vm_object
        )
        # If the VM that the hard drive is attached to is registered on the local
        # node, remove the hard drive from the LibVirt configuration
        if unregister and self.vm_object.isRegisteredLocally():
            self._unregisterLibvirt()

        # Update VM config file
        def removeDiskFromConfig(vm_config):
            del(vm_config['hard_disks'][str(self.disk_id)])

        self.vm_object.get_config_object().update_config(
            removeDiskFromConfig, 'Removed disk \'%s\' from \'%s\'' %
            (self.disk_id, self.vm_object.get_name()))

        # If the cluster is initialised, run on all nodes that the VM is available on
        if self._is_cluster_master and all_nodes:
            cluster = self._get_registered_object('cluster')
            for node in cluster.get_nodes():
                remote_disk_object = self.get_remote_object(node)
                remote_disk_object.removeFromVirtualMachine()

    def _unregisterLibvirt(self):
        """Removes the hard drive from the LibVirt configuration for the VM"""
        # Update the libvirt domain XML configuration
        def updateXML(domain_xml):
            device_xml = domain_xml.find('./devices')
            disk_xml = device_xml.find(
                './disk/target[@dev="%s"]/..' %
                self._target_dev)
            device_xml.remove(disk_xml)

        # Update libvirt configuration
        self.vm_object._editConfig(updateXML)

    def _registerLibvirt(self):
        """Register the hard drive with the Libvirt VM configuration"""

        def updateXML(domain_xml):
            drive_xml = self._generateLibvirtXml()
            device_xml = domain_xml.find('./devices')
            device_xml.append(drive_xml)

        # Update libvirt configuration
        self.vm_object._editConfig(updateXML)

    def _setVmStorageType(self):
        """Set the VM configuration storage type to the current hard drive type"""
        # Ensure VM has not already been configured with disks that
        # do not match the type specified
        number_of_disks = len(self.vm_object.getHardDriveObjects())
        current_storage_type = self.vm_object.get_config_object(
        ).get_config()['storage_type']
        if current_storage_type != self.get_type():
            if number_of_disks:
                raise StorageTypesCannotBeMixedException(
                    'The VM (%s) is already configured with %s disks' %
                    (self.vm_object.get_name(), current_storage_type))

            def updateStorageTypeConfig(config):
                config['storage_type'] = self.get_type()
            self.vm_object.get_config_object().update_config(
                updateStorageTypeConfig, 'Updated storage type for \'%s\' to \'%s\'' %
                (self.vm_object.get_name(), self.get_type()))

    @Expose(locking=True)
    def resize_volume(self, *args, **kwargs):
        """Provides an exposed method for _resize_volume
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._resize_volume(*args, **kwargs)

    def _resize_volume(self, volume, size, perform_on_nodes=False):
        """Creates a logical volume on the node/cluster"""

        try:
            # Create on local node
            System.runCommand(command_args)

            if perform_on_nodes and self._is_cluster_master:
                def remoteCommand(node):
                    remote_disk = self.get_remote_object(remote_node=node, registered=False)
                    remote_disk.resize_logical_volume(name=name, size=size)

                cluster = self._get_registered_object('cluster')
                cluster.run_remote_command(callback_method=remoteCommand,
                                           nodes=self.vm_object._get_remote_nodes())

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst resizing disk logical volume:\n" + str(e)
            )

    def activate_volume(self, volume, perform_on_nodes=False):
        """Activates a logical volume on the node/cluster"""
        # Obtain logical volume path
        volume.activate()

        if perform_on_nodes and self._is_cluster_master:
            def remoteCommand(node):
                remote_disk = self.get_remote_object(remote_node=node, registered=False)
                remote_disk.activate_volume(volume=volume)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(callback_method=remoteCommand,
                                       nodes=self.vm_object._get_remote_nodes())

    @Expose(locking=True)
    def createBackupSnapshot(self):
        """Creates a snapshot of the logical volume for backing up and locks the VM"""
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.BACKUP_VM,
            self.vm_object
        )

        # Ensure VM is registered locally
        self.vm_object.ensureRegisteredLocally()

        # Lock the VM
        self.vm_object._setLockState(LockStates.LOCKED)

        source_volume = self.get_backup_source_volume()
        backup_volume = self.get_backup_snapshot_volume()

        try:
            source_volume.snapshot_volume(backup_volume, self.SNAPSHOT_SIZE)
        except VolumeAlreadyExistsError:
            self.vm_object._setLockState(LockStates.UNLOCKED)
            raise BackupSnapshotAlreadyExistsException('Backup snapshot already exists')
        except:
            self.vm_object._setLockState(LockStates.UNLCoKED)
            raise

        self.vm_object._setLockState(LockStates.UNLOCKED)
        return backup_volume.get_path()

    @Expose(locking=True)
    def deleteBackupSnapshot(self):
        """Deletes the backup snapshot for the disk and unlocks the VM"""
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.BACKUP_VM,
            self.vm_object
        )

        try:
            self.get_backup_snapshot_volume().delete_volume()
        except VolumeDoesNotExistError:
            self.vm_object._setLockState(LockStates.UNLOCKED)
            raise BackupSnapshotDoesNotExistException(
                'The backup snapshot does not exist'
            )

        # Unlock the VM
        self.vm_object._setLockState(LockStates.UNLOCKED)

    def get_backup_source_volume(self):
        """Retrun the source volume for snapshotting for backeups"""
        raise NotImplementedError

    def get_backup_snapshot_volume(self):
        """Return a volume object for the disk object"""
        raise NotImplementedError

    @Expose(locking=True)
    def increaseSize(self, increase_size):
        """Increase the size of a VM hard drive, given the size to increase the drive by"""
        raise NotImplementedError

    def _check_exists(self):
        """Check if the disk exists"""
        raise NotImplementedError

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        raise NotImplementedError

    def create(self, size):
        """Create a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        raise NotImplementedError

    def activateDisk(self):
        """Activate the storage volume"""
        raise NotImplementedError

    def deactivateDisk(self):
        """Deactivate the storage volume"""
        raise NotImplementedError

    def preMigrationChecks(self, destination_node):
        """Determine if the disk is in a state to allow the attached VM
           to be migrated to another node"""
        raise NotImplementedError

    def preOnlineMigration(self):
        """Perform required tasks in order
           for the underlying VM to perform an
           online migration"""
        raise NotImplementedError

    def postOnlineMigration(self):
        """Perform post tasks after a VM
           has performed an online migration"""
        raise NotImplementedError

    def getSize(self):
        """Get the size of the disk (in MB)"""
        raise NotImplementedError

    def move(self, destination_node, source_node):
        """Move the storage to another node in the cluster"""
        raise NotImplementedError

    def _removeStorage(self):
        """Delete te underlying storage for the disk"""
        raise NotImplementedError

    def getDiskConfig(self):
        """Return the disk configuration for the hard drive"""
        vm_config = self.vm_object.get_config_object().get_config()
        if str(self.disk_id) in vm_config['hard_disks']:
            return vm_config['hard_disks'][str(self.disk_id)]
        else:
            return {}

    def _generateLibvirtXml(self):
        """Create a basic libvirt XML configuration for the connection to the disk"""
        # Create the base disk XML element
        device_xml = ET.Element('disk')
        device_xml.set('type', 'block')
        device_xml.set('device', 'disk')

        # Configure the interface driver to the disk
        driver_xml = ET.SubElement(device_xml, 'driver')
        driver_xml.set('name', 'qemu')
        driver_xml.set('type', 'raw')
        driver_xml.set('cache', self.CACHE_MODE)

        # Configure the source of the disk
        source_xml = ET.SubElement(device_xml, 'source')
        source_xml.set('dev', self._getDiskPath())

        # Configure the target
        target_xml = ET.SubElement(device_xml, 'target')
        target_xml.set('dev', '%s' % self._target_dev)
        target_xml.set('bus', self._getLibvirtDriver())

        return device_xml

    def _getLibvirtDriver(self):
        """Return the libvirt name of the driver for the disk"""
        return Driver[self.driver].value

    @Expose()
    def getDiskPath(self):
        """Exposed method for _getDiskPath"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_CLUSTER
        )
        return self._getDiskPath()

    def _getDiskPath(self):
        """Return the path of the raw disk image"""
        raise NotImplementedError

    def _getMCVirtConfig(self):
        """Return the MCVirt configuration for the hard drive object"""
        config = {
            'driver': self.driver,
            'storage_backend': self.get_storage_backend().name
        }
        return config

    def _getBackupLogicalVolume(self):
        """Return the storage device for the backup"""
        raise NotImplementedError

    def _getBackupSnapshotLogicalVolume(self):
        """Return the logical volume name for the backup snapshot"""
        raise NotImplementedError

    def get_storage_backend(self):
        """Return the storage backend object for the hard drive object"""
        if (not self._storage_backend or
                isinstance(self._storage_backend, str) or
                isinstance(self._storage_backend, unicode)):
            storage_backend_name = (self._storage_backend
                                    if isinstance(self._storage_backend, str) else
                                    self.getDiskConfig()['storage_backend'])
            self._storage_backend = self._get_registered_object(
                'storage_factory'
            ).get_object(storage_backend_name)
        return self._storage_backend

    def _get_volume(self, disk_name):
        """Return a storage object within the storage backend"""
        return self.get_storage_backend().get_volume(disk_name)

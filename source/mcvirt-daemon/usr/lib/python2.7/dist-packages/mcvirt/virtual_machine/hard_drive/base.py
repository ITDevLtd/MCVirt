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
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.config.hard_drive import HardDrive as HardDriveConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import ReachedMaximumStorageDevicesException
from mcvirt.utils import get_hostname
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.constants import LockStates
from mcvirt.syslogger import Syslogger


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

    def __init__(self, id_):
        """Set member variables"""
        self._id = id_

    @staticmethod
    def generate_confing()

    @property
    def id_(self):
        """Return the ID of the hard drive"""
        return self._id

    @property
    def storage_backend(self):
        """Return storage backend.
        When object is initalised from config, this is
        set to a string of the storage backend name.
        When the get_storage_backend is run, it is
        converted to a storage backend object.
        When the config is saved, the storage backend
        is saved as a string, which returns the name of
        the storage backend.
        """
        # @TODO - NEEDS REWORK NOW
        return self._storage_backend

    @property
    def libvirt_device_type(self):
        """Return the libvirt device type of the storage backend"""
        return self.get_storage_backend().libvirt_device_type

    @property
    def libvirt_source_parameter(self):
        """Return the libvirt source parameter fro storage backend"""
        return self.get_storage_backend().libvirt_source_parameter

    @property
    def driver(self):
        """Return the disk drive driver name"""
        if self._driver is None:
            self._driver = self.DEFAULT_DRIVER
        return self._driver

    @Expose()
    def get_vm_object(self):
        """Obtain the VM object for the resource"""
        # @TODO - NEEDS REWORK NOW
        vm_name = self.vm_object.get_name()
        return self._get_registered_object(
            'virtual_machine_factory').get_virtual_machine_by_name(vm_name)

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the current hard drive object on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_hard_drive_factory = node_object.get_connection('hard_drive_factory')

        hard_drive_object = remote_hard_drive_factory.getObject(self.id_)
        node_object.annotate_object(hard_drive_object)
        return hard_drive_object

    def _ensure_exists(self):
        """Ensure the disk exists on the local node"""
        self.get_storage_backend().ensure_available()
        if not self._check_exists():
            raise HardDriveDoesNotExistException(
                'Disk %s for %s does not exist' %
                (self.disk_id, self.vm_object.get_name()))

    def get_config_object(self):
        """Obtain the config object for the hard drive"""
        return HardDriveConfig(self.id_)

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
        return self.get_config_object().get_config()['type']

    def ensure_compatible(self, compare_hdd):
        """Ensure that two hard drive objects are compatible with
        one another, allowing them to be attached to the same VM
        """
        # Ensure that the type of storage (storage type, storage backend shared etc.) matches
        # disks already attached to the VM.
        # All disks attached to a VM must either be DRBD-based or not.
        # All storage backends used by a VM must shared the following attributes: type, shared
        local_storage_backend = self.get_storage_backend()
        compare_storage_backend = compare_hdd.get_storage_backend()

        if local_storage_backend.shared != compare_storage_backend.shared:
            raise InvalidStorageBackendError(
                ('Storage backend for new disk must have the same shared '
                 'status as current disks'))
        elif local_storage_backend.storage_type != compare_storage_backend.storage_type:
            raise InvalidStorageBackendError(
                ('Storage backend for new disk must be the same type '
                 'as current disks'))

    @Expose(locking=True)
    def delete(self, local_only=False):
        """Delete the logical volume for the disk"""
        # Ensure that the user has permissions to add delete storage
        # @TODO - NEEDS REWORK NOW
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM,
            self.vm_object
        )

        self._ensure_exists()

        self.vm_object.ensureUnlocked()
        self.vm_object.ensure_stopped()

        # Remove backing storage
        self._removeStorage(local_only=local_only)

        if local_only:
            nodes = [get_hostname()]
        else:
            cluster = self._get_registered_object('cluster')
            nodes = cluster.get_nodes(include_local=True)

        # Remove the hard drive from the MCVirt VM configuration
        self.removeFromVirtualMachine(nodes=nodes)

    def duplicate(self, destination_vm_object, storage_backend=None):
        """Clone the hard drive and attach it to the new VM object"""
        # @TODO - NEEDS REWORK NOW
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

    @staticmethod
    def isAvailable(node, node_drbd):
        """Returns whether the storage type is available on the node"""
        raise NotImplementedError


    def activate_volume(self, volume, perform_on_nodes=False):
        """Activates a logical volume on the node/cluster"""
        # Obtain logical volume path
        volume.activate()

        if perform_on_nodes and self._is_cluster_master:
            def remote_command(node):
                """Activate volume on remote node"""
                remote_disk = self.get_remote_object(node_object=node, registered=False)
                remote_disk.activate_volume(volume=volume)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(callback_method=remote_command,
                                       nodes=self.vm_object._get_remote_nodes())

    @Expose(locking=True)
    def createBackupSnapshot(self):
        """Creates a snapshot of the logical volume for backing up and locks the VM"""
        # @TODO - NEEDS REWORK NOW
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
        except Exception:
            self.vm_object._setLockState(LockStates.UNLCoKED)
            raise

        self.vm_object._setLockState(LockStates.UNLOCKED)
        return backup_volume.get_path()

    @Expose(locking=True)
    def deleteBackupSnapshot(self):
        """Deletes the backup snapshot for the disk and unlocks the VM"""
        # @TODO - NEEDS REWORK NOW
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
        """Perform required tasks in order for the underlying
        VM to perform an online migration
        """
        raise NotImplementedError

    def postOnlineMigration(self):
        """Perform post tasks after a VM has performed an online migration"""
        raise NotImplementedError

    def getSize(self):
        """Get the size of the disk (in bytes)"""
        raise NotImplementedError

    def move(self, destination_node, source_node):
        """Move the storage to another node in the cluster"""
        raise NotImplementedError

    def _removeStorage(self, local_only=False, remove_raw=True):
        """Delete te underlying storage for the disk"""
        raise NotImplementedError

    def getDiskConfig(self):
        """Return the disk configuration for the hard drive"""
        # @TODO - NEEDS REWORK NOW
        vm_config = self.vm_object.get_config_object().get_config()
        if str(self.disk_id) in vm_config['hard_disks']:
            return vm_config['hard_disks'][str(self.disk_id)]
        else:
            return {}

    def get_libvirt_driver(self):
        """Return the libvirt name of the driver for the disk"""
        return Driver[self.driver].value

    @Expose()
    def getDiskPath(self):
        """Exposed method for _getDiskPath"""
        # @TODO - NEEDS REWORK NOW
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_CLUSTER,
            allow_indirect=True
        )
        return self._getDiskPath()

    def _getDiskPath(self):
        """Return the path of the raw disk image"""
        raise NotImplementedError

    def _getMCVirtConfig(self):
        """Return the MCVirt configuration for the hard drive object"""
        # @TODO - NEEDS REWORK NOW
        config = {
            'driver': self.driver,
            'storage_backend': self.get_storage_backend().id_
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
            storage_backend_id = (self._storage_backend
                                  if isinstance(self._storage_backend, str) else
                                  self.getDiskConfig()['storage_backend'])
            self._storage_backend = self._get_registered_object(
                'storage_factory'
            ).get_object(storage_backend_id)
        return self._storage_backend

    def _get_volume(self, disk_name):
        """Return a storage object within the storage backend"""
        return self.get_storage_backend().get_volume(disk_name)

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
                               VolumeAlreadyExistsError,
                               InvalidStorageBackendError)
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.config.hard_drive import HardDrive as HardDriveConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import ReachedMaximumStorageDevicesException
from mcvirt.utils import get_hostname, dict_merge
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
        self._driver = None
        self._storage_backend = None
        self._base_volume_name = None

    def __eq__(self, comp):
        """Compare hard drive objects based on id"""
        # Ensure class and name of object match
        return ('__class__' in dir(comp) and
                comp.__class__ == self.__class__ and
                'id_' in dir(comp) and comp.id_ == self.id_)

    @staticmethod
    def get_id_code():
        """Return the ID code for the object"""
        return 'hd'

    @classmethod
    def generate_config(cls, driver, storage_backend, nodes, base_volume_name):
        """Generate config for hard drive"""
        return {
            'nodes': nodes,
            'driver': driver if driver else cls.DEFAULT_DRIVER,
            'storage_backend': storage_backend.id_,
            'base_volume_name': base_volume_name,
            'storage_type': cls.__name__
        }

    @property
    def id_(self):
        """Return the ID of the hard drive"""
        return self._id

    @Expose()
    def get_id(self):
        """Return ID"""
        return self.id_

    @property
    def nodes(self):
        """Return nodes that the hard drive is on"""
        return self.get_config_object().get_config()['nodes']

    @property
    def storage_backend(self):
        """Return the storage backend for the hard drive"""
        if self._storage_backend is None:
            storage_backend_id = self.get_config_object().get_config()['storage_backend']
            self._storage_backend = self._get_registered_object(
                'storage_factory').get_object(storage_backend_id)

        return self._storage_backend

    @property
    def libvirt_device_type(self):
        """Return the libvirt device type of the storage backend"""
        return self.storage_backend.libvirt_device_type

    @property
    def libvirt_source_parameter(self):
        """Return the libvirt source parameter fro storage backend"""
        return self.storage_backend.libvirt_source_parameter

    @property
    def driver(self):
        """Return the disk drive driver name"""
        # Get from config, if not cached
        if self._driver is None:
            self._driver = self.get_config_object().get_config()['driver']

        return self._driver

    @property
    def base_volume_name(self):
        """Return the disk drive driver name"""
        # Get from config, if not cached
        if self._base_volume_name is None:
            self._base_volume_name = self.get_config_object().get_config()['base_volume_name']

        return self._base_volume_name

    def get_attachment_object(self):
        """Obtain the VM object for the resource"""
        return self._get_registered_object(
            'hard_drive_attachment_factory').get_object_by_hard_drive(self)

    def get_virtual_machine(self):
        """Obtain the VM object for the resource"""
        attachment = self.get_attachment_object()

        return attachment.virtual_machine if attachment else None

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the current hard drive object on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_hard_drive_factory = node_object.get_connection('hard_drive_factory')

        hard_drive_object = remote_hard_drive_factory.get_object(self.id_)
        node_object.annotate_object(hard_drive_object)
        return hard_drive_object

    def ensure_exists(self):
        """Ensure the disk exists on the local node"""
        self.storage_backend.ensure_available()
        if not self._check_exists():
            raise HardDriveDoesNotExistException(
                'Disk %s does not exist' % self.id_)

    def get_config_object(self):
        """Obtain the config object for the hard drive"""
        return HardDriveConfig(self)

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def update_config(self, change_dict, reason, _f):
        """Update hard drive config using dict"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def update_config(config):
            """Update the MCVirt config"""
            _f.add_undo_argument(original_config=dict(config))
            dict_merge(config, change_dict)

        self.get_config_object().update_config(update_config, reason)

    @Expose()
    def undo__update_config(self, change_dict, reason, original_config=None,
                            *args, **kwargs):
        """Undo config change"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def revert_config(config):
            """Revert config"""
            config = original_config

        if original_config is not None:
            self.get_config_object().update_config(
                revert_config,
                'Revert: %s' % reason)

    def is_static(self):
        """Determine if storage is static and VM cannot be
        migrated to any node in the cluster
        """
        # By default, this is just determined whether the storage is
        # shared or not. Shared storage will allow mean storage is available
        # to any node that supports it. Otherwise, the data is only on the node
        # that the storage was created on.
        return self.storage_backend.is_static()

    @Expose(locking=True)
    def resync(self, source_node=None, auto_determine=False):
        """Resync the volume"""
        raise ResyncNotSupportedException('Resync is not supported on this storage type')

    @Expose()
    def get_type(self):
        """Return the type of storage for the hard drive"""
        return self.get_config_object().get_config()['storage_type']

    def ensure_compatible(self, compare_hdd):
        """Ensure that two hard drive objects are compatible with
        one another, allowing them to be attached to the same VM
        """
        # Ensure that the type of storage (storage type, storage backend shared etc.) matches
        # disks already attached to the VM.
        # All disks attached to a VM must either be DRBD-based or not.
        # All storage backends used by a VM must shared the following attributes: type, shared
        local_storage_backend = self.storage_backend
        compare_storage_backend = compare_hdd.storage_backend

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
        vm_object = self.get_virtual_machine()
        # Ensure that the user has permissions to add delete storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE,
            self.get_virtual_machine()
        )

        self.ensure_exists()

        if vm_object:
            vm_object.ensureUnlocked()
            vm_object.ensure_stopped()

            if not local_only:
                # Remove the hard drive from the MCVirt VM configuration
                self.get_attachment_object().delete()

        # Remove backing storage
        self._removeStorage(local_only=local_only)

        # Remove config
        self.remove_config(
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True, remote_nodes=True)
    def remove_config(self):
        """Remove hard drive config"""
        self.get_config_object().delete()

    def duplicate(self, destination_vm_object, storage_backend=None):
        """Clone the hard drive and attach it to the new VM object"""
        self.ensure_exists()

        if not storage_backend:
            storage_backend = self.storage_backend

        # Create new disk object, using the same type, size and disk_id
        new_hdd = self._get_registered_object('hard_drive_factory').create(
            size=self.get_size(), storage_type=self.get_type(),
            driver=self.driver, storage_backend=storage_backend)

        # Get path of source and new disks
        source_block_device = self._getDiskPath()
        destination_block_device = new_hdd.getDiskPath()

        # Use dd to duplicate the old disk to the new disk
        System.perform_dd(source=source_block_device,
                          destination=destination_block_device,
                          size=self.get_size())
        return new_hdd

    @staticmethod
    def isAvailable(node, node_drbd):
        """Returns whether the storage type is available on the node"""
        raise NotImplementedError

    @Expose(locking=True, remote_nodes=True)
    def activate_volume(self, volume):
        """Activates a logical volume on the node/cluster"""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)
        # Obtain logical volume path
        volume.activate()

    @Expose(locking=True)
    def create_backup_snapshot(self):
        """Creates a snapshot of the logical volume for backing up and locks the VM"""
        vm_object = self.get_virtual_machine()
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.BACKUP_VM,
            self.get_virtual_machine()
        )

        if vm_object:
            # Ensure VM is registered locally
            vm_object.ensureRegisteredLocally()

            # Lock the VM
            vm_object._setLockState(LockStates.LOCKED)

        source_volume = self.get_backup_source_volume()
        backup_volume = self.get_backup_snapshot_volume()

        try:
            source_volume.snapshot_volume(backup_volume, self.SNAPSHOT_SIZE)
        except VolumeAlreadyExistsError:
            if vm_object:
                vm_object._setLockState(LockStates.UNLOCKED)
            raise BackupSnapshotAlreadyExistsException('Backup snapshot already exists')
        except Exception:
            if vm_object:
                vm_object._setLockState(LockStates.UNLCoKED)
            raise

        if vm_object:
            vm_object._setLockState(LockStates.UNLOCKED)

        return backup_volume.get_path()

    @Expose(locking=True)
    def delete_backup_snapshot(self):
        """Deletes the backup snapshot for the disk and unlocks the VM"""
        vm_object = self.get_virtual_machine()
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.BACKUP_VM,
            vm_object
        )

        try:
            self.get_backup_snapshot_volume().delete_volume()
        except VolumeDoesNotExistError:
            if vm_object:
                vm_object._setLockState(LockStates.UNLOCKED)
            raise BackupSnapshotDoesNotExistException(
                'The backup snapshot does not exist'
            )

        # Unlock the VM
        if vm_object:
            vm_object._setLockState(LockStates.UNLOCKED)

    def get_backup_source_volume(self):
        """Retrun the source volume for snapshotting for backeups"""
        raise NotImplementedError

    def get_backup_snapshot_volume(self):
        """Return a volume object for the disk object"""
        raise NotImplementedError

    @Expose(locking=True)
    def increase_size(self, increase_size):
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

    def get_size(self):
        """Get the size of the disk (in bytes)"""
        raise NotImplementedError

    def move(self, destination_node, source_node):
        """Move the storage to another node in the cluster"""
        raise NotImplementedError

    def _removeStorage(self, local_only=False, remove_raw=True):
        """Delete te underlying storage for the disk"""
        raise NotImplementedError

    def get_libvirt_driver(self):
        """Return the libvirt name of the driver for the disk"""
        return Driver[self.driver].value

    @Expose()
    def getDiskPath(self):
        """Exposed method for _getDiskPath"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_CLUSTER,
            allow_indirect=True
        )
        return self._getDiskPath()

    def _getDiskPath(self):
        """Return the path of the raw disk image"""
        raise NotImplementedError

    def _getBackupLogicalVolume(self):
        """Return the storage device for the backup"""
        raise NotImplementedError

    def _getBackupSnapshotLogicalVolume(self):
        """Return the logical volume name for the backup snapshot"""
        raise NotImplementedError

    def _get_volume(self, disk_name):
        """Return a storage object within the storage backend"""
        return self.storage_backend.get_volume(disk_name)

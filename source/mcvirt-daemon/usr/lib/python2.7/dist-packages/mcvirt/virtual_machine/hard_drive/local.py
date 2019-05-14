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

from mcvirt.system import System
from mcvirt.exceptions import (VmAlreadyStartedException, VmIsCloneException,
                               ExternalStorageCommandErrorException,
                               DiskAlreadyExistsException,
                               CannotMigrateLocalDiskException,
                               MCVirtCommandException)
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.expose_method import Expose
from mcvirt.size_converter import SizeConverter


class Local(Base):
    """Provides operations to manage local hard drives, used by VMs."""

    MAXIMUM_DEVICES = 4
    CACHE_MODE = 'directsync'

    @classmethod
    def generate_config(cls, driver, storage_backend, nodes, base_volume_name):
        """Generate config for hard drive."""
        # If the storage backend is shared, re-assign nodes to a
        # None value, as it will be obtained by the storage backend
        if storage_backend.shared:
            nodes = None
        return super(Local, cls).generate_config(driver, storage_backend, nodes, base_volume_name)

    @property
    def nodes(self):
        """Return nodes that the hard drive is on."""
        # If storage backend is shared, return the nodes
        # that it is attached to
        if self.storage_backend.shared:
            return self.storage_backend.nodes
        return self.get_config_object().get_config()['nodes']

    @property
    def disk_name(self):
        """Return disk name."""
        return self.base_volume_name

    @staticmethod
    def isAvailable(storage_factory, node_drdb):
        """Determine if local storage is available on the node."""
        return bool(storage_factory.get_all(available_on_local_node=True))

    def _get_data_volume(self):
        """Obtain the data volume object for the disk."""
        return self._get_volume(self.disk_name)

    @Expose(locking=True)
    def increase_size(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by."""
        vm_object = self.get_virtual_machine()
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE, vm_object
        )

        # Convert disk size to bytes
        increase_size = (increase_size
                         if isinstance(increase_size, int) else
                         SizeConverter.from_string(increase_size, storage=True).to_bytes())

        # Ensure disk exists
        self.ensure_exists()

        # Ensure VM is stopped
        if vm_object and not vm_object.is_stopped:
            raise VmAlreadyStartedException('VM must be stopped before increasing disk size')

        # Ensure that VM has not been cloned and is not a clone
        if vm_object and vm_object.getCloneParent() or vm_object.getCloneChildren():
            raise VmIsCloneException('Cannot increase the disk of a cloned VM or a clone.')

        # Obtain volume for the disk and resize
        volume = self._get_data_volume()
        volume.resize(increase_size, increase=True)

    def _check_exists(self):
        """Checks if a disk exists, which is required before any operations
        can be performed on the disk."""
        return self._get_data_volume().check_exists()

    def _removeStorage(self, local_only=False, remove_raw=True):
        """Removes the backing logical volume."""
        self._get_data_volume().delete()

    def get_size(self):
        """Gets the size of the disk (in MB)"""
        return self._get_data_volume().get_size()

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object."""
        self.ensure_exists()

        # Create destination hard drive, without creating actual storage
        hard_drive_factory = self._get_registered_object('hard_drive_factory')
        new_hdd = hard_drive_factory.create(
            size=self.get_size(), storage_type=self.get_type(),
            driver=self.driver, storage_backend=self.storage_backend,
            nodes=self.nodes, skip_create=True)

        # Clone original volume to new volume
        self._get_data_volume().clone(new_hdd._get_data_volume())

        # Register with dest virtual machine
        self._get_registered_object('hard_drive_attachment_factory').create(
            destination_vm_object, new_hdd)

        return new_hdd

    def create(self, size):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration."""
        self._get_data_volume().create(size)

    def activateDisk(self):
        """Starts the disk logical volume."""
        self.ensure_exists()
        self._get_data_volume().activate()

    def deactivateDisk(self):
        """Deactivates the disk loglcal volume."""
        self._get_data_volume().deactivate()

    def preMigrationChecks(self):
        """Perform pre-migration checks."""
        # @TODO Allow migration for shared disks - worth ensuring that the disks is actually
        # available on both nodes
        if not self.storage_backend.shared:
            raise CannotMigrateLocalDiskException(
                'VMs using local disks on a non-shared backend cannot be migrated')

    def _getDiskPath(self):
        """Returns the path of the raw disk image."""
        return self._get_data_volume().get_path()

    def _getDiskName(self):
        """Returns the name of a disk logical volume, for a given VM."""
        return self.disk_name

    def get_backup_source_volume(self):
        """Retrun the source volume for snapshotting for backeups."""
        return self._get_data_volume()

    def get_backup_snapshot_volume(self):
        """Return a volume object for the disk object."""
        return self._get_volume(self.disk_name + self.SNAPSHOT_SUFFIX)

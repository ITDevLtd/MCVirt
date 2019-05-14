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

import os
import pwd
import grp
import stat

from mcvirt.storage.base import Base, BaseVolume
from mcvirt.exceptions import (InvalidStorageConfiguration,
                               VolumeAlreadyExistsError,
                               DDCommandError, VolumeDoesNotExistError,
                               ExternalStorageCommandErrorException)
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.expose_method import Expose
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.system import System


class File(Base):
    """Storage backend for file based storage."""

    @classmethod
    def check_permissions(cls, libvirt_config, directory):
        """Check permissions of directory and attempt to fix
        if libvirt user does not have permissions to read/write
        """
        require_permissions_if_owned = (
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
            stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
        )
        required_permissions_global = (
            stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        )
        libvirt_user_uid = pwd.getpwnam(libvirt_config.LIBVIRT_USER).pw_uid
        libvirt_group_gid = grp.getgrnam(libvirt_config.LIBVIRT_GROUP).gr_gid
        stat_info = os.stat(directory)

        # Check owner and group of directory
        if ((stat_info.st_uid != libvirt_user_uid or
             stat_info.st_gid != libvirt_group_gid or not
             # Check that libvirt has RWX (user and group)
             (stat_info.st_mode & require_permissions_if_owned ==
              require_permissions_if_owned)) and not
                # Otherwise, Check if 'other' has RWX
                (stat_info.st_mode & required_permissions_global ==
                 required_permissions_global)):

            # User/group are not those required for libvirt and permissions
            # of directory is not 777
            # Attempt to change directory owner/group
            os.chown(directory, libvirt_user_uid, libvirt_group_gid)
            # Append the required permissions to the current permissions
            os.chmod(directory, stat_info.st_mode | require_permissions_if_owned)

    @classmethod
    def check_exists_local(cls, directory):
        """Determine if the directory actually exists on the node."""
        return os.path.isdir(directory)

    @classmethod
    def ensure_exists(cls, location):
        """Ensure that the volume group exists."""
        if not cls.check_exists_local(location):
            raise InvalidStorageConfiguration(
                'Directory %s does not exist' % location
            )

    @classmethod
    def validate_location_name(cls, location):
        """Ensure volume group name is valid."""
        ArgumentValidator.validate_directory(location)

    @property
    def _volume_class(self):
        """Return the volume class for the storage backend."""
        return FileVolume

    @property
    def libvirt_device_type(self):
        """The libvirt property for storage path."""
        return 'file'

    @property
    def libvirt_source_parameter(self):
        """The libvirt property for source."""
        return 'file'

    @property
    def _id_volume_name(self):
        """Return the name of the identification volume."""
        # Create a hidden file with the ID
        return '.%s' % self.id_

    @Expose(remote_nodes=True)
    def get_free_space(self):
        """Return the free space in megabytes."""
        # Obtain statvfs object
        statvfs = os.statvfs(self.get_location())

        # Calculate free space in bytes by multiplying number
        # of available blocks (free for non-superuser) and the
        # block size
        free_space_b = statvfs.f_bavail * statvfs.f_frsize

        return free_space_b


class FileVolume(BaseVolume):
    """Object for handling file volume functions."""

    def _validate_name(self):
        """Ensurue name of object is valid."""
        ArgumentValidator.validate_file_name(self.name)

    def get_path(self, node=None):
        """Return the full path of a given volume."""
        return self.storage_backend.get_location(node=node) + '/' + self.name

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def create(self, size, _f=None):
        """Create volume in storage backend."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_VOLUME)
        # Ensure volume does not already exist
        if self.check_exists():
            raise VolumeAlreadyExistsError('Volume (%s) already exists' % self.name)

        try:
            # Create on local node
            System.perform_dd(source=System.WIPE, destination=self.get_path(),
                              size=size)

        except DDCommandError, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst creating disk logical volume:\n" + str(exc)
            )

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def delete(self, ignore_non_existent=False, _f=None):
        """Delete volume."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_VOLUME)
        # Determine if logical volume exists before attempting to remove it
        if not self.check_exists() and not ignore_non_existent:
            raise VolumeDoesNotExistError(
                'Volume (%s) does not exist' % self.name
            )

        try:
            os.unlink(self.get_path())

        except Exception, exc:
            raise ExternalStorageCommandErrorException(
                "Error whilst removing logical volume:\n" + str(exc)
            )

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def activate(self, _f=None):
        """Activate volume."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_VOLUME)
        # Ensure volume exists
        self.ensure_exists()

        require_permissions_if_owned = (
            stat.S_IRUSR | stat.S_IWUSR |
            stat.S_IRGRP | stat.S_IWGRP
        )
        required_permissions_global = (
            stat.S_IROTH | stat.S_IWOTH
        )
        libvirt_config = self._get_registered_object('libvirt_config')
        libvirt_user_uid = pwd.getpwnam(libvirt_config.LIBVIRT_USER).pw_uid
        libvirt_group_gid = grp.getgrnam(libvirt_config.LIBVIRT_GROUP).gr_gid
        stat_info = os.stat(self.get_path())

        # Check owner and group of directory
        if ((stat_info.st_uid != libvirt_user_uid or
             stat_info.st_gid != libvirt_group_gid or not
             # Check that libvirt has RWX (user and group)
             (stat_info.st_mode & require_permissions_if_owned ==
              require_permissions_if_owned)) and not
                # Otherwise, Check if 'other' has RWX
                (stat_info.st_mode & required_permissions_global ==
                 required_permissions_global)):

            # User/group are not those required for libvirt and permissions
            # of directory is not 777
            # Attempt to change directory owner/group
            os.chown(self.get_path(), libvirt_user_uid, libvirt_group_gid)
            # Append the required permissions to the current permissions
            os.chmod(self.get_path(), stat_info.st_mode | require_permissions_if_owned)
        return

    def is_active(self):
        """Return whether volume is activated."""
        # File has no state of 'active', just ensure it
        # exists
        return self.check_exists()

    def snapshot(self, destination_volume, size):
        """Snapshot volume."""
        # Ensure volume exists
        self.ensure_exists()

        # @TODO  Complete - maybe leave NotImplementedEror if not
        # supported, or raise better exception
        raise NotImplementedError

    def deactivate(self):
        """Deactivate volume."""
        # There is nothing to do to deactivate
        pass

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def resize(self, size, increase=True, _f=None):
        """Reszie volume."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_STORAGE_VOLUME)
        # Ensure volume exists
        self.ensure_exists()

        # @TODO Complete
        raise NotImplementedError

    def check_exists(self):
        """Determine whether logical volume exists."""
        return os.path.exists(self.get_path())

    @Expose(remote_nodes=True)
    def get_size(self):
        """Obtain the size of a logical volume."""
        self.ensure_exists()

        # Obtain size from os stat (in bytes)
        size_b = os.stat(self.get_path()).st_size

        return size_b

"""Provide auth class for managing permissions."""

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
import Pyro4
from texttable import Texttable

from mcvirt.config.mcvirt import MCVirt as MCVirtConfig
from mcvirt.exceptions import (UserNotPresentInGroup, InsufficientPermissionsException,
                               UnprivilegedUserException, InvalidPermissionGroupException,
                               DuplicatePermissionException,
                               AlreadyElevatedPermissionsError)
from mcvirt.syslogger import Syslogger
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS, PERMISSION_DESCRIPTIONS
from mcvirt.argument_validator import ArgumentValidator


class Auth(PyroObject):
    """Provides authentication and permissions for performing functions within MCVirt."""

    @staticmethod
    def check_root_privileges():
        """Ensure that the user is either running as root
        or using sudo.
        """
        if os.geteuid() == 0:
            return True
        else:
            raise UnprivilegedUserException('MCVirt must be run using sudo')

    def check_user_type(self, *user_type_names):
        """Check that the currently logged-in user is of a specified type."""
        if 'STARTUP_PERIOD' in dir(Pyro4.current_context) and Pyro4.current_context.STARTUP_PERIOD:
            return True

        if ('INTERNAL_REQUEST' in dir(Pyro4.current_context) and
                Pyro4.current_context.INTERNAL_REQUEST):
            return True

        user_object = self._get_registered_object('mcvirt_session').get_current_user_object()
        if user_object.__class__.__name__ in user_type_names:
            return True
        else:
            return False

    def assert_user_type(self, *user_type_names, **kwargs):
        """Ensure that the currently logged in user is of a specified type."""
        allow_indirect = kwargs['allow_indirect'] if 'allow_indirect' in kwargs else False
        if (not (self.check_user_type(*user_type_names) or
                 (allow_indirect and self.has_permission_asserted()))):
            raise InsufficientPermissionsException(
                'User must be one of the following: %s' % ', '.join(user_type_names)
            )

    def has_permission_asserted(self):
        """Return whether permission has been asserted using assert_permission"""
        if 'PERMISSION_ASSERTED' in dir(Pyro4.current_context):
            return Pyro4.current_context.PERMISSION_ASSERTED is True
        else:
            return False

    def set_permission_asserted(self):
        """Called when user has passed a permission requirement"""
        # Mark in the context that user has passed permission checks
        if 'PERMISSION_ASSERTED' in dir(Pyro4.current_context):
            Pyro4.current_context.PERMISSION_ASSERTED = True

    def assert_permission(self, permission_enum, vm_object=None, allow_indirect=False):
        """Use check_permission function to determine if a user has a given permission
        and throws an exception if the permission is not present.
        """
        if self.check_permission(permission_enum, vm_object):
            self.set_permission_asserted()
            return True
        elif allow_indirect and self.has_permission_asserted():
            Syslogger.logger().debug('Already asserted permission and indirect')
            return True
        else:
            # If the permission has not been found, throw an exception explaining that
            # the user does not have permission
            raise InsufficientPermissionsException('User does not have the'
                                                   ' required permission: %s' %
                                                   permission_enum.name)

    def check_permission(self, permission_enum, vm_object=None, user_object=None):
        """Check that the user has a given permission, either globally through MCVirt or for a
        given VM.
        """
        if 'STARTUP_PERIOD' in dir(Pyro4.current_context) and Pyro4.current_context.STARTUP_PERIOD:
            return True

        if ('INTERNAL_REQUEST' in dir(Pyro4.current_context) and
                Pyro4.current_context.INTERNAL_REQUEST):
            return True

        # If the user is a superuser, all permissions are attached to the user
        if self.is_superuser():
            return True

        # If the permission is in the list of elevated permissions, grant access
        if ('ELEVATED_PERMISSIONS' in dir(Pyro4.current_context) and
                permission_enum in Pyro4.current_context.ELEVATED_PERMISSIONS):
            return True

        if user_object is None:
            user_object = self._get_registered_object('mcvirt_session').get_current_user_object()

        if vm_object:
            self._convert_remote_object(vm_object)

        # Check the users permissions and determine if the permission is present
        if permission_enum in user_object.get_permissions(virtual_machine=vm_object):
            return True

        return False

    @Expose()
    def is_superuser(self):
        """Determine if the current user is a superuser of MCVirt."""
        # Cluster users can do anything
        if self.check_user_type('ClusterUser'):
            return True
        user_object = self._get_registered_object('mcvirt_session').get_proxy_user_object()
        username = user_object.get_username()
        superusers = self.get_superusers()

        return username in superusers

    def get_superusers(self):
        """Return a list of superusers"""
        mcvirt_config = MCVirtConfig()
        return mcvirt_config.get_config()['superusers']

    @Expose(locking=True)
    def add_superuser(self, user_object, ignore_duplicate=False):
        """Add a new superuser."""
        assert isinstance(self._convert_remote_object(user_object),
                          self._get_registered_object('user_factory').USER_CLASS)
        ArgumentValidator.validate_boolean(ignore_duplicate)

        # Ensure the user is a superuser
        if not self.is_superuser():
            raise InsufficientPermissionsException(
                'User must be a superuser to manage superusers'
            )
        user_object = self._convert_remote_object(user_object)
        username = user_object.get_username()

        mcvirt_config = MCVirtConfig()

        # Ensure user is not already a superuser
        if username not in self.get_superusers():
            def update_config(config):
                """Append superuser to MCVirt config"""
                config['superusers'].append(username)
            mcvirt_config.update_config(update_config, 'Added superuser \'%s\'' % username)

        elif not ignore_duplicate:
            raise DuplicatePermissionException(
                'User \'%s\' is already a superuser' % username
            )

        if self._is_cluster_master:
            def remote_command(connection):
                """Add superuser to remote node"""
                remote_user_factory = connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(user_object.get_username())
                remote_auth = connection.get_connection('auth')
                remote_auth.add_superuser(remote_user, ignore_duplicate=ignore_duplicate)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    @Expose(locking=True)
    def delete_superuser(self, user_object):
        """Remove a superuser."""
        assert isinstance(self._convert_remote_object(user_object),
                          self._get_registered_object('user_factory').USER_CLASS)

        # Ensure the user is a superuser
        if not self.is_superuser():
            raise InsufficientPermissionsException(
                'User must be a superuser to manage superusers'
            )

        user_object = self._convert_remote_object(user_object)
        username = user_object.get_username()

        # Ensure user to be removed is a superuser
        if username not in self.get_superusers():
            raise UserNotPresentInGroup('User \'%s\' is not a superuser' % username)

        mcvirt_config = MCVirtConfig()

        def update_config(config):
            """Remove superuser from MCVirt config"""
            config['superusers'].remove(username)
        mcvirt_config.update_config(update_config, 'Removed \'%s\' from superuser group' %
                                                   username)

        if self._is_cluster_master:
            def remote_command(connection):
                """Remove superuser from remote nodes"""
                remote_user_factory = connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(user_object.get_username())
                remote_auth = connection.get_connection('auth')
                remote_auth.delete_superuser(remote_user)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    def copy_permissions(self, source_vm, dest_vm):
        """Copy the permissions from a given VM to this VM.
        This functionality is used whilst cloning a VM
        """
        # Obtain permission configuration for source VM
        permission_config = source_vm.get_config_object().getPermissionConfig()

        # Add permissions configuration from source VM to destination VM
        def add_user_to_group(vm_config):
            """Copy permissions to config"""
            vm_config['permissions'] = permission_config

        dest_vm.get_config_object().update_config(add_user_to_group,
                                                  'Copied permission from \'%s\' to \'%s\'' %
                                                  (source_vm.get_name(), dest_vm.get_name()))

    @Expose()
    def list_permissions(self):
        """Create a tabular view of permissions and permission descriptions"""
        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Permission', 'Description'))

        # Set column alignment and widths
        table.set_cols_width((25, 90))
        table.set_cols_align(('l', 'l'))

        for permission in sorted(PERMISSION_DESCRIPTIONS.keys()):
            table.add_row((
                permission,
                PERMISSION_DESCRIPTIONS[permission]
            ))
        return table.draw()


class ElevatePermission(object):
    """Object to allow temporary permission elevation"""

    def __init__(self, *permissions):
        """Store permissions in member variable"""
        self.permissions = permissions

    def __enter__(self):
        """Assign the elevated permissions"""
        # Check whether elevated permissions have already been assigned
        if ('ELEVATED_PERMISSIONS' in dir(Pyro4.current_context) and
                Pyro4.current_context.ELEVATED_PERMISSIONS):
            raise AlreadyElevatedPermissionsError('Permissions already elevated')
        else:
            Syslogger.logger().info('Elevating permissions: %s' % str(self.permissions))
            Pyro4.current_context.ELEVATED_PERMISSIONS = self.permissions

    def __exit__(self, type, value, traceback):
        """Remove elevated permissions"""
        if 'ELEVATED_PERMISSIONS' in dir(Pyro4.current_context):
            del Pyro4.current_context.ELEVATED_PERMISSIONS
            Syslogger.logger().info('de-elevating permissions: %s' % str(self.permissions))
        else:
            Syslogger.logger().warning(
                'Elevated permissions disaapeared before removing')

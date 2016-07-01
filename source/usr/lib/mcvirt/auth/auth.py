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

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import (UserNotPresentInGroup, InsufficientPermissionsException,
                               UnprivilegedUserException, InvalidPermissionGroupException,
                               DuplicatePermissionException)
from mcvirt.rpc.lock import locking_method
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.auth.permissions import PERMISSIONS, PERMISSION_GROUPS
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
        if Pyro4.current_context.STARTUP_PERIOD:
            return True

        user_object = self._get_registered_object('mcvirt_session').get_current_user_object()
        if user_object.__class__.__name__ in user_type_names:
            return True
        else:
            return False

    def assert_user_type(self, *user_type_names):
        """Ensure that the currently logged in user is of a specified type."""
        if not self.check_user_type(*user_type_names):
            raise InsufficientPermissionsException(
                'User must be on the following: %s' % ', '.join(user_type_names)
            )

    def assert_permission(self, permission_enum, vm_object=None):
        """Use check_permission function to determine if a user has a given permission
        and throws an exception if the permission is not present.
        """
        if self.check_permission(permission_enum, vm_object):
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
        if Pyro4.current_context.STARTUP_PERIOD:
            return True

        # If the user is a superuser, all permissions are attached to the user
        if self.is_superuser():
            return True

        if user_object is None:
            user_object = self._get_registered_object('mcvirt_session').get_current_user_object()

        # Determine if the type of user has the permissions
        if permission_enum in user_object.PERMISSIONS:
            return True

        # Check the global permissions configuration to determine
        # if the user has been granted the permission
        mcvirt_config = MCVirtConfig()
        mcvirt_permissions = mcvirt_config.getPermissionConfig()
        if self.check_permission_in_config(mcvirt_permissions, user_object.get_username(),
                                           permission_enum):
            return True

        # If a vm_object has been passed, check the VM
        # configuration file for the required permissions
        if vm_object:
            vm_config_object = vm_object.get_config_object()
            vm_config = vm_config_object.getPermissionConfig()

            # Determine if the user has been granted the required permissions
            # in the VM configuration file
            if (self.check_permission_in_config(vm_config, user_object.get_username(),
                                                permission_enum)):
                return True

        return False

    def check_permission_in_config(self, permission_config, user, permission_enum):
        """Read permissions config and determines if a user has a given permission."""
        # Ititerate through the permission groups on the VM
        for (permission_group, users) in permission_config.items():

            # Check that the group, defined in the VM, is defined in this class
            if permission_group not in PERMISSION_GROUPS.keys():
                raise InvalidPermissionGroupException(
                    'Permissions group, %s, does not exist' % permission_group
                )

            # Check if user is part of the group and the group contains
            # the required permission
            if ((user in users) and
                    (permission_enum in PERMISSION_GROUPS[permission_group])):
                return True

        return False

    def is_superuser(self):
        """Determine if the current user is a superuser of MCVirt."""
        # Cluster users can do anything
        if self.check_user_type('ClusterUser'):
            return True
        user_object = self._get_registered_object('mcvirt_session').get_proxy_user_object()
        username = user_object.get_username()
        superusers = self.get_superusers()

        return ((username in superusers))

    def get_superusers(self):
        """Return a list of superusers"""
        mcvirt_config = MCVirtConfig()
        return mcvirt_config.get_config()['superusers']

    @Pyro4.expose()
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
                config['superusers'].append(username)
            mcvirt_config.update_config(update_config, 'Added superuser \'%s\'' % username)

        elif not ignore_duplicate:
            raise DuplicatePermissionException(
                'User \'%s\' is already a superuser' % username
            )

        if self._is_cluster_master:
            def remote_command(connection):
                remote_user_factory = connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(user_object.get_username())
                remote_auth = connection.get_connection('auth')
                remote_auth.add_superuser(remote_user, ignore_duplicate=ignore_duplicate)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    @Pyro4.expose()
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
        if (username not in self.get_superusers()):
            raise UserNotPresentInGroup('User \'%s\' is not a superuser' % username)

        mcvirt_config = MCVirtConfig()

        def update_config(config):
            config['superusers'].remove(username)
        mcvirt_config.update_config(update_config, 'Removed \'%s\' from superuser group' %
                                                   username)

        if self._is_cluster_master:
            def remote_command(connection):
                remote_user_factory = connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(user_object.get_username())
                remote_auth = connection.get_connection('auth')
                remote_auth.delete_superuser(remote_user)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    @Pyro4.expose()
    @locking_method()
    def add_user_permission_group(self, permission_group, user_object,
                                  vm_object=None, ignore_duplicate=False):
        """Add a user to a permissions group on a VM object."""
        assert permission_group in PERMISSION_GROUPS.keys()
        assert isinstance(self._convert_remote_object(user_object),
                          self._get_registered_object('user_factory').USER_CLASS)
        assert isinstance(self._convert_remote_object(vm_object),
                          self._get_registered_object(
                              'virtual_machine_factory').VIRTUAL_MACHINE_CLASS)
        ArgumentValidator.validate_boolean(ignore_duplicate)

        # Check if user running script is able to add users to permission group
        if not (self.is_superuser() or
                (vm_object and self.assert_permission(PERMISSIONS.MANAGE_VM_USERS,
                                                      vm_object) and
                 permission_group == 'user')):
            raise InsufficientPermissionsException('VM owners cannot add manager other owners')

        user_object = self._convert_remote_object(user_object)
        vm_object = self._convert_remote_object(vm_object) if vm_object is not None else None
        username = user_object.get_username()

        # Check if user is already in the group
        if (vm_object):
            config_object = vm_object.get_config_object()
        else:
            config_object = MCVirtConfig()

        if (username not in self.get_users_in_permission_group(permission_group, vm_object)):

            # Add user to permission configuration for VM
            def add_user_to_config(config):
                config['permissions'][permission_group].append(username)

            config_object.update_config(add_user_to_config, 'Added user \'%s\' to group \'%s\'' %
                                                            (username, permission_group))

            # @TODO FIX ME
            if self._is_cluster_master:
                cluster_object = self._get_registered_object('cluster')
                vm_name = vm_object.get_name() if vm_object else None
                cluster_object.run_remote_command('auth-add_user_permission_group',
                                                  {'permission_group': permission_group,
                                                   'username': username,
                                                   'vm_name': vm_name})

        elif not ignore_duplicate:
            raise DuplicatePermissionException(
                'User \'%s\' already in group \'%s\'' % (username, permission_group)
            )

    @Pyro4.expose()
    @locking_method()
    def delete_user_permission_group(self, permission_group, user_object, vm_object=None):
        """Remove user from a permissions group on a VM object."""
        assert permission_group in PERMISSION_GROUPS.keys()
        assert isinstance(self._convert_remote_object(user_object),
                          self._get_registered_object('user_factory').USER_CLASS)
        assert isinstance(self._convert_remote_object(vm_object),
                          self._get_registered_object(
                              'virtual_machine_factory').VIRTUAL_MACHINE_CLASS)
        # Check if user running script is able to remove users to permission group
        if not (self.is_superuser() or
                (self.assert_permission(PERMISSIONS.MANAGE_VM_USERS, vm_object) and
                 permission_group == 'user') and vm_object):
            raise InsufficientPermissionsException('Does not have required permission')

        user_object = self._convert_remote_object(user_object)
        vm_object = self._convert_remote_object(vm_object) if vm_object is not None else None
        username = user_object.get_username()

        # Check if user exists in the group
        if username not in self.get_users_in_permission_group(permission_group, vm_object):
            raise UserNotPresentInGroup('User \'%s\' not in group \'%s\'' %
                                        (username, permission_group))

        if vm_object:
            config_object = vm_object.get_config_object()
            vm_name = vm_object.get_name()
        else:
            config_object = MCVirtConfig()
            vm_name = None

        # Remove user from permission configuration for VM
        def remove_user_from_group(config):
            config['permissions'][permission_group].remove(username)

        config_object.update_config(remove_user_from_group,
                                    'Removed user \'%s\' from group \'%s\'' %
                                    (username, permission_group))

        # @TODO FIX ME
        if self._is_cluster_master:
            cluster_object = self._get_registered_object('cluster')
            cluster_object.run_remote_command('auth-delete_user_permission_group',
                                              {'permission_group': permission_group,
                                               'username': username,
                                               'vm_name': vm_name})

    def get_permission_groups(self):
        """Return list of user groups."""
        return PERMISSION_GROUPS.keys()

    def copy_permissions(self, source_vm, dest_vm):
        """Copy the permissions from a given VM to this VM.
        This functionality is used whilst cloning a VM
        """
        # Obtain permission configuration for source VM
        permission_config = source_vm.get_config_object().getPermissionConfig()

        # Add permissions configuration from source VM to destination VM
        def add_user_to_group(vm_config):
            vm_config['permissions'] = permission_config

        dest_vm.get_config_object().update_config(add_user_to_group,
                                                  'Copied permission from \'%s\' to \'%s\'' %
                                                  (source_vm.get_name(), dest_vm.get_name()))

    def get_users_in_permission_group(self, permission_group, vm_object=None):
        """Obtain a list of users in a given group, either in the global permissions or
        for a specific VM.
        """
        if vm_object:
            permission_config = vm_object.get_config_object().getPermissionConfig()
        else:
            mcvirt_config = MCVirtConfig()
            permission_config = mcvirt_config.getPermissionConfig()

        if permission_group in permission_config.keys():
            return permission_config[permission_group]
        else:
            raise InvalidPermissionGroupException(
                'Permission group \'%s\' does not exist' % permission_group
            )

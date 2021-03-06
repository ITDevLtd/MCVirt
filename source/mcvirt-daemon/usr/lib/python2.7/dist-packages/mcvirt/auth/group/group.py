"""Provide class for managing groups."""

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

import hashlib
import datetime

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.exceptions import (GropuInUseError,
                               DuplicatePermissionException,
                               UserNotPresentInGroup,
                               GroupAlreadyContainsPermissionError,
                               GroupDoesNotContainPermissionError)
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.argument_validator import ArgumentValidator


class Group(PyroObject):
    """Object for groups."""

    @staticmethod
    def get_id_code():
        """Return the ID code for the object."""
        return 'gp'

    def __init__(self, id_):
        """Setup member variables."""
        self._id = id_

    def __eq__(self, comp):
        """Allow for comparison of group baesd on id."""
        # Ensure class and name of object match
        if ('__class__' in dir(comp) and
                comp.__class__ == self.__class__ and
                'id_' in dir(comp) and comp.id_ == self.id_):
            return True

        # Otherwise return false
        return False

    @property
    def id_(self):
        """Return the ID of the storage backend."""
        return self._id

    @property
    def name(self):
        """Return name of storage backend."""
        return self.get_config()['name']

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the group object on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_group_factory = node_object.get_connection('group_factory')
        remote_group = remote_group_factory.get_object(self.id_)
        node_object.annotate_object(remote_group)

        return remote_group

    @Expose(locking=True)
    def add_user(self, user, virtual_machine=None, ignore_duplicate=False):
        """Add uesr to group."""
        assert isinstance(self.po__convert_remote_object(user),
                          self.po__get_registered_object('user_factory').USER_CLASS)
        if virtual_machine:
            assert isinstance(self.po__convert_remote_object(virtual_machine),
                              self.po__get_registered_object(
                                  'virtual_machine_factory').VIRTUAL_MACHINE_CLASS)
        ArgumentValidator.validate_boolean(ignore_duplicate)

        if virtual_machine is not None:
            virtual_machine = self.po__convert_remote_object(virtual_machine)

        # Check if user running script is able to add users to permission group
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUP_MEMBERS,
                                                              vm_object=virtual_machine)

        # Convert remote objects
        user = self.po__convert_remote_object(user)

        # Ensure that the user is not already in the group
        if (user in self.get_users(virtual_machine=virtual_machine) and
                not ignore_duplicate):
            raise DuplicatePermissionException('User %s already in group %s' %
                                               (user.get_username(), self.name))

        cluster = self.po__get_registered_object('cluster')
        if virtual_machine:
            # Convert remote objects
            self.add_user_to_vm_config(
                user, virtual_machine,
                nodes=cluster.get_nodes(include_local=True))
        else:
            self.add_user_to_config(user, nodes=cluster.get_nodes(include_local=True))

    @Expose(locking=True, remote_nodes=True, undo_method='remove_user_from_config')
    def add_user_to_config(self, user):
        """Add user to group config."""
        # Check permissions
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        # Convert remote objects
        user = self.po__convert_remote_object(user)

        def update_config(config):
            """Update config."""
            config['groups'][self.id_]['users'].append(user.get_username())
        MCVirtConfig().update_config(update_config, 'Add user %s to group %s' %
                                     (user.get_username(), self.name))

    @Expose(locking=True, remote_nodes=True, undo_method='remove_user_from_vm_config')
    def add_user_to_vm_config(self, user, virtual_machine):
        """Add user to group config."""
        # Check permissions
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        # Convert remote objects
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        user = self.po__convert_remote_object(user)

        def update_config(config):
            """Update VM config."""
            # Add group config to VM if it doesn't exist
            if self.id_ not in config['permissions']['groups']:
                config['permissions']['groups'][self.id_] = self.get_vm_config(
                    virtual_machine=virtual_machine)

            config['permissions']['groups'][self.id_]['users'].append(user.get_username())
        virtual_machine.get_config_object().update_config(
            update_config, 'Add user %s to group %s' %
            (user.get_username(), self.name))

    @Expose(locking=True)
    def remove_user(self, user, virtual_machine=None):
        """Remove user from group."""
        # Check permissions
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUP_MEMBERS,
                                                              vm_object=virtual_machine)

        # Convert remote objects
        if virtual_machine is not None:
            virtual_machine = self.po__convert_remote_object(virtual_machine)
        user = self.po__convert_remote_object(user)

        # Ensure that the user is not already in the group
        if user not in self.get_users(virtual_machine=virtual_machine):
            raise UserNotPresentInGroup('User %s not in group %s' %
                                        (user.get_username(), self.name))

        cluster = self.po__get_registered_object('cluster')
        if virtual_machine:
            self.remove_user_from_vm_config(user, virtual_machine,
                                            nodes=cluster.get_nodes(include_local=True))
        else:
            self.remove_user_from_config(user, nodes=cluster.get_nodes(include_local=True))

    @Expose(locking=True, remote_nodes=True, undo_method='add_user_to_config')
    def remove_user_from_config(self, user):
        """Add user to group config."""
        # Check permissions
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        # Convert remote objects
        user = self.po__convert_remote_object(user)

        def update_config(config):
            """Update config."""
            config['groups'][self.id_]['users'].remove(user.get_username())
        MCVirtConfig().update_config(update_config, 'Add user %s from group %s' %
                                     (user.get_username(), self.name))

    @Expose(locking=True, remote_nodes=True, undo_method='add_user_to_vm_config')
    def remove_user_from_vm_config(self, user, virtual_machine):
        """Add user to group config."""
        # Check permissions
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        # Convert remote objects
        virtual_machine = self.po__convert_remote_object(virtual_machine)
        user = self.po__convert_remote_object(user)

        def update_config(config):
            """Update VM config."""
            # Add group config to VM if it doesn't exist
            if self.id_ not in config['permissions']['groups']:
                config['permissions']['groups'][self.id_] = self.get_vm_config(
                    virtual_machine=virtual_machine)

            config['permissions']['groups'][self.id_]['users'].remove(user.get_username())
        virtual_machine.get_config_object().update_config(
            update_config, 'Remove user %s from group %s' %
            (user.get_username(), self.name))

    def in_use(self):
        """Determine if there are any users in the group."""
        vm_factory = self.po__get_registered_object('virtual_machine_factory')
        for virtual_machine in [None] + vm_factory.get_all_virtual_machines():
            if self.get_users(virtual_machine=virtual_machine):
                return True

        return False

    @Expose(locking=True)
    def delete(self):
        """Shared function to remove storage."""
        # Check permissions
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUPS)

        # Determine if storage backend if used by VMs
        if self.in_use():
            raise GropuInUseError('Storage backend cannot be removed as it contains users')

        # Remove VM from MCVirt configuration
        cluster = self.po__get_registered_object('cluster')
        self.remove_config(nodes=cluster.get_nodes(include_local=True))

    @Expose(remote_nodes=True)
    def remove_config(self):
        """Remove VM from MCVirt configuration."""
        # Check permissions
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def update_mcvirt_config(config):
            """Remove object from mcvirt config."""
            del config['groups'][self.id_]
        MCVirtConfig().update_config(
            update_mcvirt_config,
            'Removed storage backend \'%s\' from global MCVirt config' %
            self.name
        )

        # Remove cached pyro object
        storage_factory = self.po__get_registered_object('group_factory')
        if self.id_ in storage_factory.CACHED_OBJECTS:
            self.po__unregister_object()
            del storage_factory.CACHED_OBJECTS[self.id_]

    def get_config(self):
        """Get config for storage backend."""
        return self.po__get_registered_object('group_factory').get_config()[self.id_]

    def get_vm_config(self, virtual_machine):
        """Return the configuration for the group in a VM."""
        # Check permissions
        vm_groups = virtual_machine.get_config_object().getPermissionConfig()['groups']
        if self.id_ in vm_groups:
            return vm_groups[self.id_]
        else:
            # If the VM does not contain a config for the group
            return {
                'users': []
            }

    def get_permissions(self):
        """Return permissions assigned to the group."""
        return [PERMISSIONS[permission] for permission in self.get_config()['permissions']]

    @Expose()
    def get_users_remote(self, *args, **kwargs):
        """Old style method for exposing the get_users method.
        Difficult to use other methods, since get_users is used to determine permissions
        """
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUPS)
        return self.get_users(*args, **kwargs)

    def get_users(self, virtual_machine=None):
        """Return the users assigned to the group, either global or a VM."""
        user_factory = self.po__get_registered_object('user_factory')
        if virtual_machine is None:
            return [user_factory.get_user_by_username(username)
                    for username in self.get_config()['users']]
        else:
            virtual_machine = self.po__convert_remote_object(virtual_machine)
            return [user_factory.get_user_by_username(user)
                    for user in self.get_vm_config(virtual_machine)['users']]

    def is_user_member(self, user, virtual_machine=None):
        """Determe if user is a member of the group."""
        return user in self.get_users(virtual_machine=virtual_machine)

    @Expose(locking=True)
    def add_permission(self, permission):
        """Add a permission to the group."""
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUPS)

        # Check that permission is valid
        ArgumentValidator.validate_permission(permission)

        permission_enum = PERMISSIONS[permission]
        if permission_enum in self.get_permissions():
            raise GroupAlreadyContainsPermissionError(
                'Group \'%s\' already contains permission \'%s\'' %
                (self.name, permission))

        cluster = self.po__get_registered_object('cluster')
        self.add_permission_to_config(permission, nodes=cluster.get_nodes(include_local=True))

    @Expose(locking=True, remote_nodes=True, undo_method='remove_permission_from_config')
    def add_permission_to_config(self, permission):
        """Add permission from group config."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser', allow_indirect=True)

        def update_config(config):
            """Update group config."""
            config['groups'][self.id_]['permissions'].append(permission)
        MCVirtConfig().update_config(
            update_config,
            'Remove permission \'%s\' from group \'%s\'' % (permission, self.name))

    @Expose(locking=True)
    def remove_permission(self, permission):
        """Remove a permission from the group."""
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUPS)

        ArgumentValidator.validate_permission(permission)
        permission_enum = PERMISSIONS[permission]

        if permission_enum not in self.get_permissions():
            raise GroupDoesNotContainPermissionError(
                'Group \'%s\' does not contain permission \'%s\'' %
                (self.name, permission))

        cluster = self.po__get_registered_object('cluster')
        self.remove_permission_from_config(permission, nodes=cluster.get_nodes(include_local=True))

    @Expose(locking=True, remote_nodes=True, undo_method='add_permission_to_config')
    def remove_permission_from_config(self, permission):
        """Remove permission from group config."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser', allow_indirect=True)

        def update_config(config):
            """Update group config."""
            config['groups'][self.id_]['permissions'].remove(permission)
        MCVirtConfig().update_config(update_config, 'Remove permission \'%s\' from group \'%s\'' %
                                     (permission, self.name))

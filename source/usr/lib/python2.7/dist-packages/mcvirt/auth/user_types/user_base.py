"""Provide a base class for user objects."""

# Copyright (c) 2016 - I.T. Dev Ltd
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
import random
import string
from binascii import hexlify
from pbkdf2 import crypt
import Pyro4

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import UserDoesNotExistException, InvalidUserTypeException
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS


class UserBase(PyroObject):
    """Base object for users (both user and automated)."""

    USER_PREFIX = None
    CAN_GENERATE = False
    PERMISSIONS = []
    CLUSTER_USER = False
    DISTRIBUTED = True
    CAN_CREATE = True
    SEARCH_ORDER = 1
    UNIQUE = False
    EXPIRE_SESSION = False
    LOCALLY_MANAGED = False

    @classmethod
    def get_all_usernames(cls):
        """Return all local users"""
        user_config = MCVirtConfig().get_config()['users']
        users = []
        for username in user_config:
            if user_config[username]['user_type'] == cls.__name__:
                users.append(username)
        return users

    def __eq__(self, comp):
        """Allow for comparison of user objects"""
        # Ensure class and name of object match
        if ('__class__' in dir(comp) and
                comp.__class__ == self.__class__ and
                'get_username' in dir(comp) and comp.get_username() == self.get_username()):
            return True

        # Otherwise return false
        return False

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the user object on a remote node"""
        if not self.DISTRIBUTED:
            raise InvalidUserTypeException('Cannot get remote object of non-distributed user')

        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_user_factory = node_object.get_connection('user_factory')
        remote_user = remote_user_factory.get_user_by_username(self.get_username())
        node_object.annotate_object(remote_user)

        return remote_user

    @Expose()
    def is_superuser(self):
        """Determine if the user is a superuser of MCVirt."""
        username = self.get_username()
        superusers = self._get_registered_object('auth').get_superusers()

        return ((username in superusers))

    @property
    def allow_proxy_user(self):
        """Connection users can proxy for another user."""
        return False

    @classmethod
    def _check_exists(cls, username):
        """Check the MCVirt config to determine if a given user exists."""
        return (username in cls.get_all_usernames())

    @staticmethod
    def _generate_salt():
        """Generate random salt for the user's password,"""
        return hexlify(os.urandom(32))

    def __init__(self, username):
        """Store member variables and ensures that the user exists."""
        self.username = username
        self._ensure_exists()

    @Expose()
    def is_locally_managed(self):
        """Determine if user is locally managed"""
        return self.LOCALLY_MANAGED

    @Expose()
    def get_username(self):
        """Return the username of the current user"""
        return self.username

    def _ensure_exists(self):
        """Ensure that the current user exists in the MCVirt configuration"""
        if not self.__class__._check_exists(self.get_username()):
            raise UserDoesNotExistException('User %s does not exist' %
                                            self.get_username())

    @Expose()
    def get_config(self):
        """Return the configuration of the user."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_USERS
        )
        return self._get_config()

    def _get_config(self):
        """Return the config hash for the current user"""
        return MCVirtConfig().get_config()['users'][self.get_username()]

    def get_user_type(self):
        """Return the user type of the user"""
        return self._get_config()['user_type']

    def _check_password(self, password):
        """Check the given password against the stored password for the user."""
        password_hash = self._hash_password(password)
        config = self._get_config()
        return (password_hash == config['password'])

    def _get_password_salt(self):
        """Return the user's salt"""
        return self._get_config()['salt']

    @Expose()
    def set_password(self, new_password):
        """Default functionality for password change is to throw an exception"""
        raise InvalidUserTypeException('Cannot change password for this type of user')

    def _set_password(self, new_password):
        """Set the password for the current user"""
        password_hash = self._hash_password(new_password)

        def update_config(config):
            config['users'][self.get_username()]['password'] = password_hash
        MCVirtConfig().update_config(
            update_config, 'Updated password for \'%s\'' % self.get_username()
        )

        if self.DISTRIBUTED and self._is_cluster_master:
            def remote_command(node_connection):
                remote_user_factory = node_connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(self.get_username())
                node_connection.annotate_object(remote_user)
                remote_user.set_password(new_password)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    def _hash_password(self, password):
        """Hash a password, using the current user's salt"""
        return self.__class__._hash_string(password, self._get_password_salt())

    @staticmethod
    def _hash_string(string, salt):
        """Hash string using salt"""
        return crypt(string, salt, iterations=1000)

    @staticmethod
    def generate_password(length, numeric_only=False):
        """Return a randomly generated password"""
        characers = string.ascii_letters
        if not numeric_only:
            characers += string.digits + '!@#$%^&*()'
        random.seed(os.urandom(1024))
        return ''.join(random.choice(characers) for i in range(length))

    def get_permissions(self, virtual_machine=None):
        """Obtain the list of permissions that the user has"""
        # Get the list of hard coded permission for the user type
        permissions = list(self.PERMISSIONS)

        # Add additional user global permissions
        permissions += [PERMISSIONS[permission]
                        for permission in self._get_config()['global_permissions']]

        # Obtain list of permissions assigned by groups that the
        # user is a member of
        group_factory = self._get_registered_object('group_factory')
        for group in group_factory.get_all():
            if (group.is_user_member(user=self) or
                    (virtual_machine and
                     group.is_user_member(user=self, virtual_machine=virtual_machine))):
                permissions += group.get_permissions()

        if virtual_machine:
            virtual_machine = self._convert_remote_object(virtual_machine)

            # Get VM user permission overrides and add permissions
            vm_permission_overrides = virtual_machine.get_config_object(). \
                getPermissionConfig()['users']
            if self.get_username() in vm_permission_overrides:
                permissions += [PERMISSIONS[permission]
                                for permission in vm_permission_overrides[self.get_username()]]

        from mcvirt.syslogger import Syslogger
        Syslogger.logger().debug(virtual_machine)

        return permissions

    @Expose(locking=True)
    def delete(self):
        """Delete the current user from MCVirt config"""
        auth_object = self._get_registered_object('auth')
        auth_object.assert_permission(
            PERMISSIONS.MANAGE_USERS
        )

        # Remove any global/VM-specific permissions
        if self.get_username() in auth_object.get_superusers():
            auth_object.delete_superuser(self)
        group_factory = self._get_registered_object('group_factory')
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for virtual_machine in [None] + virtual_machine_factory.getAllVirtualMachines():
            for group in group_factory.get_all():
                if self.get_username() in group.get_users(virtual_machine=virtual_machine):
                    group.remove_user(user=self, virtual_machine=virtual_machine)

        cluster = self._get_registered_object('cluster')
        # If the user is distributed, remove from all nodes
        nodes = cluster.get_nodes(include_local=True) if self.DISTRIBUTED else None
        self.remove_user_config(nodes=nodes)

    @Expose(locking=True, remote_nodes=True)
    def remove_user_config(self):
        """Remove user from MCVirt config"""
        def update_config(config):
            """Update config"""
            del config['users'][self.get_username()]
        MCVirtConfig().update_config(update_config, 'Deleted user \'%s\'' % self.get_username())

        # Unregister and remove cached object
        if self.get_username() in self._get_registered_object('user_factory').CACHED_OBJECTS:
            del(self._get_registered_object('user_factory').CACHED_OBJECTS[self.get_username()])
        self.unregister_object()

    @staticmethod
    def get_default_config():
        """Return the default configuration for the user type."""
        return {
            'password': None,
            'salt': None,
            'user_type': None
        }

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
from mcvirt.exceptions import UserDoesNotExistException
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.lock import locking_method


class UserBase(PyroObject):
    """Base object for users (both user and automated)."""

    USER_PREFIX = None
    CAN_GENERATE = False
    PERMISSIONS = []
    CLUSTER_USER = False
    DISTRIBUTED = True

    @property
    def allow_proxy_user(self):
        """Connection users can proxy for another user."""
        return False

    @staticmethod
    def _check_exists(username):
        """Check the MCVirt config to determine if a given user exists."""
        return (username in MCVirtConfig().get_config()['users'])

    @staticmethod
    def _generate_salt():
        """Generate random salt for the user's password,"""
        return hexlify(os.urandom(32))

    def __init__(self, username):
        """Store member variables and ensures that the user exists."""
        self.username = username
        self._ensure_exists()

    @Pyro4.expose()
    def get_username(self):
        """Return the username of the current user"""
        return self.username

    def _ensure_exists(self):
        """Ensure that the current user exists in the MCVirt configuration"""
        if not self.__class__._check_exists(self.get_username()):
            raise UserDoesNotExistException('User %s does not exist' %
                                            self.get_username())

    @Pyro4.expose()
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

    @Pyro4.expose()
    @locking_method()
    def delete(self):
        """Delete the current user from MCVirt config"""
        auth_object = self._get_registered_object('auth')
        auth_object.assert_permission(
            PERMISSIONS.MANAGE_USERS
        )

        # Remove any global/VM-specific permissions
        if self.get_username() in auth_object.get_superusers():
            auth_object.delete_superuser(self)

        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for virtual_machine in [None] + virtual_machine_factory.getAllVirtualMachines():
            for permission_group in auth_object.get_permission_groups():
                if (self.get_username() in auth_object.get_users_in_permission_group(
                        permission_group, vm_object=virtual_machine)):
                    auth_object.delete_user_permission_group(
                        permission_group, self, vm_object=virtual_machine
                    )

        def update_config(config):
            del config['users'][self.get_username()]
        MCVirtConfig().update_config(update_config, 'Deleted user \'%s\'' % self.get_username())

        if self.DISTRIBUTED and self._is_cluster_master:
            def remote_command(node_connection):
                remote_user_factory = node_connection.get_connection('user_factory')
                remote_user = remote_user_factory.get_user_by_username(self.get_username())
                node_connection.annotate_object(remote_user)
                remote_user.delete()

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    @staticmethod
    def get_default_config():
        """Return the default configuration for the user type."""
        return {
            'password': None,
            'salt': None,
            'user_type': None
        }

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
from mcvirt.rpc.lock import lockingMethod


class UserBase(PyroObject):
    """Base object for users (both user and automated)"""

    USER_PREFIX = None
    CAN_GENERATE = False
    PERMISSIONS = []
    CLUSTER_USER = False

    @property
    def allow_proxy_user(self):
        """Connection users can proxy for another user."""
        return False

    @staticmethod
    def _checkExists(username):
        """Checks the MCVirt config to determine if a given user exists"""
        return (username in MCVirtConfig().get_config()['users'])

    @staticmethod
    def _generateSalt():
        """Generates random salt for the user's password"""
        return hexlify(os.urandom(32))

    def __init__(self, username):
        """Stores member variables and ensures that the user exists"""
        self.username = username
        self._ensureExists()

    @Pyro4.expose()
    def getUsername(self):
        """Returns the username of the current user"""
        return self.username

    def _ensureExists(self):
        """Ensure that the current user exists in the MCVirt configuration"""
        if not self.__class__._checkExists(self.getUsername()):
            raise UserDoesNotExistException('User %s does not exist' %
                                            self.getUsername())

    @Pyro4.expose()
    def get_config(self):
        """Returns the configuration of the user"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_USERS
        )
        return self._get_config()

    def _get_config(self):
        """Returns the config hash for the current user"""
        return MCVirtConfig().get_config()['users'][self.getUsername()]

    def getUserType(self):
        """Returns the user type of the user"""
        return self._get_config()['user_type']

    def _checkPassword(self, password):
        """Checks a given password against the stored password for the user"""
        password_hash = self._hashPassword(password)
        config = self._get_config()
        return (password_hash == config['password'])

    def _getPasswordSalt(self):
        """Returns the user's salt"""
        return self._get_config()['salt']

    def _setPassword(self, new_password):
        """Sets the password for the current user"""
        password_hash = self._hashPassword(new_password)

        def update_config(config):
            config['users'][self.getUsername()]['password'] = password_hash
        MCVirtConfig().update_config(update_config, 'Updated password for \'%s\'' % self.getUsername())

    def _hashPassword(self, password):
        """Hashes a password, using the current user's salt"""
        return self.__class__._hashString(password, self._getPasswordSalt())

    @staticmethod
    def _hashString(string, salt):
        """Hash string using salt"""
        return crypt(string, salt, iterations=1000)

    @staticmethod
    def generatePassword(length, numeric_only=False):
        """Returns a randomly generated password"""
        characers = string.ascii_letters
        if not numeric_only:
            characers += string.digits + '!@#$%^&*()'
        random.seed(os.urandom(1024))
        return ''.join(random.choice(characers) for i in range(length))

    @Pyro4.expose()
    @lockingMethod()
    def delete(self):
        """Deletes current user from MCVirt config"""
        auth_object = self._get_registered_object('auth')
        auth_object.assert_permission(
            PERMISSIONS.MANAGE_USERS
        )

        # Remove any global/VM-specific permissions
        if self.getUsername() in auth_object.get_superusers():
            auth_object.delete_superuser(self)

        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for virtual_machine in [None] + virtual_machine_factory.getAllVirtualMachines():
            for permission_group in auth_object.get_permission_groups():
                if self.getUsername() in auth_object.get_users_in_permission_group(permission_group,
                                                                               vm_object=virtual_machine):
                    auth_object.delete_user_permission_group(permission_group, self,
                                                          vm_object=virtual_machine)

        def update_config(config):
            del config['users'][self.getUsername()]
        MCVirtConfig().update_config(update_config, 'Deleted user \'%s\'' % self.getUsername())

    @staticmethod
    def get_default_config():
        return {
            'password': None,
            'salt': None,
            'user_type': None
        }

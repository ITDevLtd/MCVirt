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
from binascii import hexlify
from pbkdf2 import crypt
import Pyro4

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.mcvirt import MCVirtException


class UserDoesNotExistException(MCVirtException):
    """The specified user does not exist"""
    pass


class UserBase(object):
    """Base object for users (both user and automated)"""

    USER_PREFIX = None
    CAN_GENERATE = False

    @staticmethod
    def _checkExists(username):
        """Checks the MCVirt config to determine if a given user exists"""
        return (username in MCVirtConfig().getConfig()['users'])

    @staticmethod
    def _generateSalt():
        """Generates random salt for the user's password"""
        return hexlify(os.urandom(32))

    def __init__(self, username):
        """Stores member variables and ensures that the user exists"""
        self._username = username
        self._ensureExists()

    @Pyro4.expose()
    def getUsername(self):
        """Returns the username of the current user"""
        return self._username

    def _ensureExists(self):
        """Ensure that the current user exists in the MCVirt configuration"""
        if not self.__class__._checkExists(self.getUsername()):
            raise UserDoesNotExistException('User %s does not exist' %
                                            self.getUsername())

    def _getConfig(self):
        """Returns the config hash for the current user"""
        return MCVirtConfig().getConfig()['users'][self.getUsername()]

    def getUserType(self):
        """Returns the user type of the user"""
        return self._getConfig()['user_type']

    def _checkPassword(self, password):
        """Checks a given password against the stored password for the user"""
        password_hash = self._hashPassword(password)
        config = self._getConfig()
        return (password_hash == config['password'])

    def _getPasswordSalt(self):
        """Returns the user's salt"""
        return self._getConfig()['salt']

    def _setPassword(self, new_password):
        """Sets the password for the current user"""
        password_hash = self._hashPassword(new_password)
        def updateConfig(config):
            config['users'][self.getUsername()]['password'] = password_hash
        MCVirtConfig().updateConfig(updateConfig, 'Updated password for \'%s\'' % self.getUsername())

    def _hashPassword(self, password):
        """Hashes a password, using the current user's salt"""
        return self.__class__._hashString(password, self._getPasswordSalt())

    @staticmethod
    def _hashString(string, salt):
        """Hash string using salt"""
        return crypt(string, salt, iterations=1000)

    def delete(self):
        """Deletes current user from MCVirt config"""
        def updateConfig(config):
            del config['users'][self.getUsername()]
        MCVirtConfig().updateConfig(updateConfig, 'Deleted user \'%s\'' % self.getUsername())

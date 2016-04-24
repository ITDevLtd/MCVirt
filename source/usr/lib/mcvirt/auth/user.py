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
from PBKDF2 import PBKDF2
from Crypto.Cipher import AES

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.mcvirt import MCVirtException


class UserDoesNotExistException(MCVirtException):
    """The specified user does not exist"""
    pass


class IncorrectCredentials(MCVirtException):
    """The supplied credentials are incorrect"""
    pass


class OldPasswordIncorrect(MCVirtException):
    """The old password is not correct"""
    pass


class User(object):
    """Provides an interaction with the local user backend"""

    @staticmethod
    def authenticate(username, password):
        """Attempts to authenticate a user, using username/password"""
        try:
            user_object = User(username)
            if user_object._checkPassword(password):
                return user_object
        except UserDoesNotExistException:
            pass
        raise IncorrectCredentials('Incorrect username/password')

    @staticmethod
    def _checkExists(username):
        """Checks the MCVirt config to determine if a given user exists"""
        return (username in MCVirtConfig().getConfig()['users'])

    @staticmethod
    def _generateSalt():
        """Generates random salt for the user's password"""
        return hexlify(os.urandom(8))

    @staticmethod
    def create(username, password):
        """Creates a user"""
        # Ensure that there is not a duplicate user
        if User._checkExists(username):
            raise UserAlreadyExists('There is a user with the same username \'%s\'' %
                                    username)

        # Generate password salt for user and hash password
        salt = User._generateSalt()
        hashed_password = User._hashString(password, salt)

        # Create config for user and update MCVirt config
        user_config = {
            'password': hashed_password,
            'salt': salt
        }
        def updateConfig(config):
            config['users'][username] = user_config
        MCVirtConfig().updateConfig(updateConfig, 'Create user \'%s\'' % username)

    def __init__(self, username):
        """Stores member variables and ensures that the user exists"""
        self._username = username
        self._ensureExists()

    def getUsername(self):
        """Returns the username of the current user"""
        return self._username

    def _ensureExists(self):
        """Ensure that the current user exists in the MCVirt configuration"""
        if not User._checkExists(self.getUsername()):
            raise UserDoesNotExistException('User %s does not exist' %
                                            self.username)

    def _getConfig(self):
        """Returns the config hash for the current user"""
        return MCVirtConfig().getConfig()['users'][self.getUsername()]

    def changePassword(old_password, new_password):
        """Changes the current user's password"""
        if not self._checkPassword(old_password):
            raise OldPasswordIncorrect('Old password is not correct')
        self._setPassword(new_password)

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
        return User._hashString(password, self._getPasswordSalt())

    @staticmethod
    def _hashString(string, salt):
        """Hash string using salt"""
        return PBKDF2(string, salt).read(32)

    def delete(self):
        """Deletes current user from MCVirt config"""
        def updateConfig(config):
            del config['users'][self.getUsername()]
        MCVirtConfig().updateConfig(updateConfig, 'Deleted user \'%s\'' % self.getUsername())

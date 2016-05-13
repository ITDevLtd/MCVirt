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

import Pyro4

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import IncorrectCredentials, InvalidUsernameException
from user import User
from mcvirt.rpc.pyro_object import PyroObject
from user_base import UserBase
from user import User
from connection_user import ConnectionUser
from auth import Auth


class Factory(PyroObject):
    """Class for obtaining user objects"""

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    def get_user_types(self):
        """Returns the available user classes"""
        return UserBase.__subclasses__()

    def ensure_valid_user_type(self, user_type):
        """Ensures that a given user_type is valid"""
        if user_type not in self.get_user_types():
            raise InvalidUserType('An invalid user type has been passed')

    def create(self, username, password, user_type=User):
        """Creates a user"""
        self.mcvirt_instance.getAuthObject().assertPermission(
            Auth.PERMISSIONS.MANAGE_USERS
        )

        # Ensure that username is not part of a reserved namespace
        for user_class in self.get_user_types():
            if (user_class is not user_type and
                    user_class.USER_PREFIX is not None and
                    username.startswith(user_class.USER_PREFIX)):
                raise InvalidUsernameException(
                    'Username is within a reserved namespace'
                )

        # Ensure that there is not a duplicate user
        if UserBase._checkExists(username):
            raise UserAlreadyExists('There is a user with the same username \'%s\'' %
                                    username)

        # Ensure valid user type
        self.ensure_valid_user_type(user_type)

        # Generate password salt for user and hash password
        salt = UserBase._generateSalt()
        hashed_password = UserBase._hashString(password, salt)

        # Create config for user and update MCVirt config
        user_config = {
            'password': hashed_password,
            'salt': salt,
            'user_type': user_type.__name__
        }
        def updateConfig(config):
            config['users'][username] = user_config
        MCVirtConfig().updateConfig(updateConfig, 'Create user \'%s\'' % username)

    def authenticate(self, username, password):
        """Attempts to authenticate a user, using username/password"""
        try:
            user_object = self.get_user_by_username(username)
            if user_object._checkPassword(password):
                return user_object
        except UserDoesNotExistException as e:
            pass
        raise IncorrectCredentials('Incorrect username/password')

    @Pyro4.expose()
    def get_user_by_username(self, username):
        """Obtains a user object for the given username"""
        generic_object = UserBase(username=username)
        user_object = None
        for user_class in UserBase.__subclasses__():
            if str(user_class.__name__) == str(generic_object.getUserType()):
                user_object = user_class(username=username)
                self._register_object(user_object)
                return user_object

        raise InvalidUserType('Failed to determine user type for %s' %
                              generic_object.getUsername())

    def get_all_users(self):
        """Returns all the users, excluding built-in users"""
        return self.get_all_user_objects(user_class=User)

    def get_all_user_objects(self, user_class=None):
        """Returns the user objects for all users, optionally filtered by user type"""
        if user_class is not None:
            # Ensure valid user type
            self.ensure_valid_user_type(user_class)

        # Obtain all usernames
        all_usernames = MCVirtConfig().getConfig()['users'].keys()
        user_objects = []
        for username in all_usernames:
            user_object = self.get_user_by_username(username)

            # Is the user object is the same type as specified, or the user type
            # has not been specified, add to user objects list
            if user_class is None or user_object.getUserType() == user_class.__name__:
                user_objects.append(user_object)

        # Return found user objects
        return user_objects

    def generate_user(self, user_type):
        """Removes any existing connection user and generates credentials for a new
          connection user"""
        # Ensure valid user type
        self.ensure_valid_user_type(user_type)

        # Ensure that users can be generated
        if not user_type.CAN_GENERATE:
            raise InvalidUserType('Users of type \'%s\' cannot be generated' %
                                  user_type.__name__)

        # Delete any old connection users
        for old_user_object in self.get_all_user_objects(user_class=user_type):
            old_user_object.delete()

        username = user_type.USER_PREFIX + user_type.generatePassword(32, numeric_only=True)
        password = user_type.generatePassword(32)
        self.create(username=username, password=password, user_type=user_type)
        return username, password

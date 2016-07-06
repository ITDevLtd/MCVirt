"""Provide factory class to create/obtain users."""

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
from mcvirt.exceptions import (IncorrectCredentials, InvalidUsernameException,
                               UserDoesNotExistException, InvalidUserTypeException,
                               UserAlreadyExistsException, BlankPasswordException)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.auth.user_base import UserBase
from mcvirt.auth.user import User
from mcvirt.auth.connection_user import ConnectionUser
from mcvirt.auth.cluster_user import ClusterUser
from mcvirt.auth.permissions import PERMISSIONS


class Factory(PyroObject):
    """Class for obtaining user objects"""

    USER_CLASS = UserBase

    def get_user_types(self):
        """Return the available user classes."""
        return [User, ConnectionUser, ClusterUser]

    def ensure_valid_user_type(self, user_type):
        """Ensure that a given user_type is valid."""
        if user_type not in self.get_user_types():
            raise InvalidUserTypeException('An invalid user type has been passed')

    @Pyro4.expose()
    def create(self, username, password, user_type=User):
        """Create a user."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_USERS
        )

        if password == '':
            raise BlankPasswordException('Password cannot be blank')

        # Ensure that username is not part of a reserved namespace
        for user_class in self.get_user_types():
            if (user_class is not user_type and
                    user_class.USER_PREFIX is not None and
                    username.startswith(user_class.USER_PREFIX)):
                raise InvalidUsernameException(
                    'Username is within a reserved namespace'
                )

        # Ensure that there is not a duplicate user
        if UserBase._check_exists(username):
            raise UserAlreadyExistsException('There is a user with the same username \'%s\'' %
                                             username)

        # Ensure valid user type
        self.ensure_valid_user_type(user_type)

        # Generate password salt for user and hash password
        salt = UserBase._generate_salt()
        hashed_password = UserBase._hash_string(password, salt)

        # Create config for user and update MCVirt config
        user_config = user_type.get_default_config()
        user_config['password'] = hashed_password
        user_config['salt'] = salt
        user_config['user_type'] = user_type.__name__

        def update_config(config):
            config['users'][username] = user_config
        MCVirtConfig().update_config(update_config, 'Create user \'%s\'' % username)

        if user_type.DISTRIBUTED and self._is_cluster_master:
            # Create the user on the other nodes in the cluster
            def remote_command(node_connection):
                remote_user_factory = node_connection.get_connection('user_factory')
                remote_user_factory.create(username, password)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    @Pyro4.expose()
    def add_config(self, username, user_config):
        """Add a user config to the local node."""
        # Ensure this is being run as a Cluster User
        self._get_registered_object('auth').check_user_type('ClusterUser')

        def update_config(config):
            config['users'][username] = user_config
        MCVirtConfig().update_config(update_config, 'Adding user %s' % username)

    def authenticate(self, username, password):
        """Attempt to authenticate a user, using username/password."""
        try:
            user_object = self.get_user_by_username(username)
            if user_object._check_password(password):
                return user_object
        except UserDoesNotExistException:
            pass
        raise IncorrectCredentials('Incorrect username/password')

    @Pyro4.expose()
    def get_user_by_username(self, username):
        """Obtain a user object for the given username."""
        generic_object = UserBase(username=username)
        for user_class in UserBase.__subclasses__():
            if str(user_class.__name__) == str(generic_object.get_user_type()):
                user_object = user_class(username=username)
                self._register_object(user_object)
                return user_object

        raise InvalidUserTypeException('Failed to determine user type for %s' %
                                       generic_object.get_username())

    @Pyro4.expose()
    def get_all_users(self):
        """Return all the users, excluding built-in users."""
        return self.get_all_user_objects(user_class=User)

    @Pyro4.expose()
    def get_all_user_objects(self, user_class=None):
        """Return the user objects for all users, optionally filtered by user type."""
        if user_class is not None:
            # Ensure valid user type
            self.ensure_valid_user_type(user_class)

        # Obtain all usernames
        all_usernames = MCVirtConfig().get_config()['users'].keys()
        user_objects = []
        for username in all_usernames:
            user_object = self.get_user_by_username(username)

            # Is the user object is the same type as specified, or the user type
            # has not been specified, add to user objects list
            if user_class is None or user_object.get_user_type() == user_class.__name__:
                user_objects.append(user_object)

        # Return found user objects
        return user_objects

    def generate_user(self, user_type):
        """Remove any existing connection user and generates credentials for a new
        connection user.
        """
        # Ensure valid user type
        self.ensure_valid_user_type(user_type)

        # Ensure that users can be generated
        if not user_type.CAN_GENERATE:
            raise InvalidUserTypeException('Users of type \'%s\' cannot be generated' %
                                           user_type.__name__)

        # Delete any old connection users
        for old_user_object in self.get_all_user_objects(user_class=user_type):
            old_user_object.delete()

        username = user_type.USER_PREFIX + user_type.generate_password(32, numeric_only=True)
        password = user_type.generate_password(32)
        self.create(username=username, password=password, user_type=user_type)
        return username, password

    @Pyro4.expose()
    def get_cluster_user_by_node(self, node):
        """Obtain a cluster user for a given node"""
        for user in self.get_all_user_objects(user_class=ClusterUser):
            if user.node == node:
                return user
        raise UserDoesNotExistException('No user found for node %s' % node)

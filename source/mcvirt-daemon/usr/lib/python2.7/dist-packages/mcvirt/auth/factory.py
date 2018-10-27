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

from texttable import Texttable

from mcvirt.config.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import (IncorrectCredentials, InvalidUsernameException,
                               UserDoesNotExistException, InvalidUserTypeException,
                               UserAlreadyExistsException, BlankPasswordException)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.user_types.user_base import UserBase
from mcvirt.auth.user_types.local_user import LocalUser
from mcvirt.auth.user_types.cluster_user import ClusterUser
from mcvirt.auth.user_types.ldap_user import LdapUser
from mcvirt.auth.user_types.drbd_hook_user import DrbdHookUser
from mcvirt.auth.permissions import PERMISSIONS


class Factory(PyroObject):
    """Class for obtaining user objects"""

    USER_CLASS = UserBase
    CACHED_OBJECTS = {}

    def get_user_types(self):
        """Return the available user classes."""
        return sorted(UserBase.__subclasses__(),
                      key=lambda user_class: user_class.SEARCH_ORDER)

    def ensure_valid_user_type(self, user_type):
        """Ensure that a given user_type is valid."""
        for user_type_itx in self.get_user_types():
            if user_type is user_type_itx or user_type == user_type_itx.__name__:
                return user_type_itx

        raise InvalidUserTypeException('An invalid user type has been passed')

    @Expose()
    def generate_password(self):
        """Generate password"""
        return UserBase.generate_password(10)

    @Expose()
    def create(self, username, password, user_type=LocalUser):
        """Create a user."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_USERS
        )

        if not user_type.CAN_CREATE:
            raise InvalidUserTypeException('Cannot create this type of user')

        if not password:
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
        if user_type.check_exists(username):
            raise UserAlreadyExistsException('There is a user with the same username \'%s\'' %
                                             username)

        # Ensure valid user type
        user_type = self.ensure_valid_user_type(user_type)

        # Generate password salt for user and hash password
        salt = user_type._generate_salt()
        hashed_password = user_type._hash_string(password, salt)

        # Create config for user and update MCVirt config
        user_config = user_type.get_default_config()
        user_config['password'] = hashed_password
        user_config['salt'] = salt
        user_config['user_type'] = user_type.__name__
        user_config['global_permissions'] = []

        def update_config(config):
            """Update user config in MCVirt config"""
            config['users'][username] = user_config
        MCVirtConfig().update_config(update_config, 'Create user \'%s\'' % username)

        if user_type.DISTRIBUTED and self._is_cluster_master:
            # Create the user on the other nodes in the cluster
            def create_user_remote(node_connection):
                """Create user on remote node"""
                remote_user_factory = node_connection.get_connection('user_factory')
                remote_user_factory.create(username, password)

            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(create_user_remote)

    @Expose()
    def add_config(self, username, user_config):
        """Add a user config to the local node."""
        # Ensure this is being run as a Cluster User
        self._get_registered_object('auth').check_user_type('ClusterUser')

        def update_config(config):
            """Add user config to MCVirt config"""
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

    @Expose()
    def get_user_by_username(self, username):
        """Obtain a user object for the given username."""
        for user_class in self.get_user_types():
            if username in user_class.get_all_usernames():
                if username not in Factory.CACHED_OBJECTS:
                    Factory.CACHED_OBJECTS[username] = user_class(username=username)
                    self._register_object(Factory.CACHED_OBJECTS[username])
                return Factory.CACHED_OBJECTS[username]

        raise UserDoesNotExistException('User %s does not exist' %
                                        username)

    @Expose()
    def get_all_users(self):
        """Return all the users, excluding built-in users."""
        user_classes = filter(lambda user_class: not user_class.CLUSTER_USER,
                              self.get_user_types())
        return self.get_all_user_objects(user_classes=user_classes)

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses"""
        # Set permissions as having been checked, as listing VMs
        # does not require permissions
        self._get_registered_object('auth').set_permission_asserted()

        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES | Texttable.HLINES)
        table.header(('Name', 'User Type', 'Groups'))

        # Set column alignment and widths
        table.set_cols_width((15, 10, 40))
        table.set_cols_align(('l', 'l', 'l'))

        for user in self.get_all_users():
            table.add_row((
                user.get_username(),
                user.get_user_type(),
                ', '.join([group.name for group in user.get_groups()])
            ))
        return table.draw()

    @Expose()
    def get_all_user_objects(self, user_classes=[]):
        """Return the user objects for all users, optionally filtered by user type."""
        if len(user_classes):
            # Ensure valid user type
            for itx, user_class in enumerate(user_classes):
                user_classes[itx] = self.ensure_valid_user_type(user_class)
        else:
            user_classes = self.get_user_types()

        user_objects = []
        for user_class in user_classes:

            # Generate user objects for each user that is returned by the user class.
            for username in user_class.get_all_usernames():
                user_objects.append(self.get_user_by_username(username))

        # Return found user objects
        return user_objects

    def generate_user(self, user_type):
        """Remove any existing connection user and generates credentials for a new
        connection user.
        """
        # Ensure valid user type
        user_type = self.ensure_valid_user_type(user_type)

        # Ensure that users can be generated
        if not user_type.CAN_GENERATE:
            raise InvalidUserTypeException('Users of type \'%s\' cannot be generated' %
                                           user_type.__name__)

        if user_type.UNIQUE:
            # Delete any old connection users
            for old_user_object in self.get_all_user_objects(user_classes=[user_type]):
                old_user_object.delete()

        username = user_type.USER_PREFIX + user_type.generate_password(32, numeric_only=True)
        password = user_type.generate_password(32)
        self.create(username=username, password=password, user_type=user_type)
        return username, password

    @Expose()
    def get_cluster_user_by_node(self, node):
        """Obtain a cluster user for a given node"""
        for user in self.get_all_user_objects(user_classes=[ClusterUser]):
            if user.node == node:
                return user
        raise UserDoesNotExistException('No user found for node %s' % node)

"""Provide class for creating groups."""

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

from texttable import Texttable

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose, Transaction
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.auth.group.group import Group
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.exceptions import (GroupAlreadyExistsError,
                               GroupDoesNotExistError)


class Factory(PyroObject):
    """Provides a factory for creating group objects"""

    OBJECT_TYPE = 'group'
    CACHED_OBJECTS = {}
    GROUP_CONFIG_KEY = 'groups'

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the group factory on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('group_factory')

    @Expose(locking=True)
    def create(self, name):
        """Create storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_GROUPS)

        # Ensure storage backend does not already exist with same name
        if self.get_id_by_name(name):
            raise GroupAlreadyExistsError('Group already exists: %s' % name)

        t = Transaction()

        # Ensure that nodes are valid
        cluster = self._get_registered_object('cluster')

        # Generate ID for the group
        id_ = Group.generate_id(name)

        # Ensure name is valid
        ArgumentValidator.validate_group_name(name)

        # Create config
        config = {'name': name,
                  'permissions': [],
                  'users': []}

        self.create_config(id_, config, nodes=cluster.get_nodes(include_local=True))

        group_object = self.get_object(id_)

        t.finish()

        return group_object

    def get_all(self):
        """Get all of group objects"""
        return [self.get_object(id_) for id_ in self.get_config().keys()]

    @Expose(remote_nodes=True)
    def create_config(self, id_, config):
        """Create config for the storage backend"""
        # Check permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        # Add new storage backend to MCVirt config
        def update_config(mcvirt_config):
            """Update MCVirt config"""
            mcvirt_config[self.GROUP_CONFIG_KEY][id_] = config
        MCVirtConfig().update_config(update_config, 'Add group %s' % config['name'])

    @Expose()
    def undo__create_config(self, id_, config):
        """Undo the create config"""
        # Check permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def update_config(mcvirt_config):
            """Update MCVirt config"""
            del mcvirt_config[self.GROUP_CONFIG_KEY][id_]
        MCVirtConfig().update_config(update_config, 'Remove group %s' % config['name'])

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses"""
        # Set permissions as having been checked, as listing VMs
        # does not require permissions
        self._get_registered_object('auth').set_permission_asserted()

        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES | Texttable.HLINES)
        table.header(('Name', 'Permissions', 'Global users'))

        # Set column alignment and widths
        table.set_cols_width((15, 40, 40))
        table.set_cols_align(('l', 'l', 'l'))

        for group in self.get_all():
            table.add_row((
                group.name,
                ', '.join([str(perm) for perm in group.get_permissions()]),
                ', '.join([user.get_username() for user in group.get_users(virtual_machine=None)])
            ))
        return table.draw()

    def get_config(self):
        """Return the configs for storage backends"""
        return MCVirtConfig().get_config()[Factory.GROUP_CONFIG_KEY]

    def get_id_by_name(self, name):
        """Determine the ID of a storage backend by name"""
        config = self.get_config()

        # Check each
        for id_ in config:
            if config[id_]['name'] == name:
                return id_

        # Return False if it does not exist
        return False

    def check_exists(self, id_):
        """Determine if a storage backend exists by ID"""
        return id_ in self.get_config().keys()

    @Expose()
    def get_object(self, id_):
        """Return a group object by id"""
        # Ensure exists
        if not self.check_exists(id_):
            raise GroupDoesNotExistError('Group does not exist: %s' % id_)

        # Create group object and cache
        if id_ not in Factory.CACHED_OBJECTS:
            group_object = Group(id_)
            self._register_object(group_object)
            Factory.CACHED_OBJECTS[id_] = group_object

        return Factory.CACHED_OBJECTS[id_]

    @Expose()
    def get_object_by_name(self, name):
        """Return group object by name"""
        object_id = self.get_id_by_name(name)
        if not object_id:
            raise GroupDoesNotExistError('Group does not exist: %s' % name)
        return self.get_object(object_id)

    @Expose()
    def set_config(self, group_config):
        """Add a user config to the local node."""
        # Ensure this is being run as a Cluster User
        self._get_registered_object('auth').check_user_type('ClusterUser')

        def update_config(config):
            """Set group config"""
            config['groups'] = group_config
        MCVirtConfig().update_config(update_config, 'Updating groups')

"""Provide class for regular MCVirt interactive users"""

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

from mcvirt.auth.user_types.user_base import UserBase
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.expose_method import Expose
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.exceptions import (UserAlreadyHasPermissionError,
                               UserDoesNotHavePermissionError)


class LocalUser(UserBase):
    """Provides an interaction with the local user backend"""

    EXPIRE_SESSION = True

    @Expose()
    def set_password(self, new_password):
        """Change the current user's password."""
        # Check that the current user is the same as this user, or that current user has
        # the correct permissions
        actual_user = self.po__get_registered_object('mcvirt_session').get_proxy_user_object()
        if actual_user.get_username() != self.get_username():
            self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)

        self._set_password(new_password)

    @Expose(locking=True)
    def add_permission(self, permission):
        """Add permissoin to the user"""
        # Check permissions
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)
        ArgumentValidator.validate_permission(permission)

        if permission in self._get_config()['global_permissions']:
            raise UserAlreadyHasPermissionError('User already has permission %s' % permission)

        cluster = self.po__get_registered_object('cluster')
        self.add_permission_to_user_config(nodes=cluster.get_nodes(include_local=True),
                                           permission=permission)

    @Expose(locking=True, remote_nodes=True)
    def add_permission_to_user_config(self, permission):
        """Add permission to user config"""
        def update_config(config):
            """Add permission to user config"""
            config['users'][self.get_username()]['global_permissions'].append(permission)
        MCVirtConfig().update_config(
            update_config, 'Add permission to user \'%s\'' % self.get_username()
        )

    @Expose(locking=True)
    def remove_permission(self, permission):
        """Remove permissoin from the user"""
        # Check permissions
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)
        ArgumentValidator.validate_permission(permission)

        if permission not in self._get_config()['global_permissions']:
            raise UserDoesNotHavePermissionError('User does not have permission %s' % permission)

        cluster = self.po__get_registered_object('cluster')
        self.remove_permission_from_user_config(nodes=cluster.get_nodes(include_local=True),
                                                permission=permission)

    @Expose(locking=True, remote_nodes=True)
    def remove_permission_from_user_config(self, permission):
        """Remove permission from user config"""
        def update_config(config):
            """Add permission to user config"""
            config['users'][self.get_username()]['global_permissions'].remove(permission)
        MCVirtConfig().update_config(
            update_config, 'Remove permission from user \'%s\'' % self.get_username()
        )

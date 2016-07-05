"""Provide class for managing connection users."""

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

from mcvirt.auth.user_base import UserBase
from mcvirt.auth.cluster_user import ClusterUser
from mcvirt.auth.permissions import PERMISSIONS


class ConnectionUser(UserBase):
    """User type for initial connection users"""

    USER_PREFIX = 'mcv-connection-'
    CAN_GENERATE = True
    PERMISSIONS = [PERMISSIONS.MANAGE_USERS]
    CLUSTER_USER = True
    DISTRIBUTED = False

    @property
    def allow_proxy_user(self):
        """Connection users can proxy for another user."""
        return True

    @Pyro4.expose()
    def create_cluster_user(self, host):
        """Create a cluster user for the remote node."""
        assert self.get_username() == Pyro4.current_context.username
        auth = self._pyroDaemon.registered_factories['auth']
        auth.assert_user_type('ConnectionUser')
        user_factory = self._pyroDaemon.registered_factories['user_factory']
        username, password = user_factory.generate_user(ClusterUser)
        user_factory.get_user_by_username(username).update_host(host)
        self.delete()
        return username, password

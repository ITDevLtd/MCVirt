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

from user_base import UserBase
from cluster_user import ClusterUser
from permissions import PERMISSIONS

class ConnectionUser(UserBase):
    """User type for initial connection users"""

    USER_PREFIX = 'mcv-connection-'
    CAN_GENERATE = True
    PERMISSIONS = [PERMISSIONS.MANAGE_USERS]

    @property
    def ALLOW_PROXY_USER(self):
        """Connection users can proxy for another user"""
        return True

    @Pyro4.expose()
    def createClusterUser(self, host):
        assert self.getUsername() == Pyro4.current_context.username
        auth = self._pyroDaemon.registered_factories['auth']
        auth.assert_user_type('ConnectionUser')
        user_factory = self._pyroDaemon.registered_factories['user_factory']
        username, password = user_factory.generate_user(ClusterUser)
        user_factory.get_user_by_username(username).updateHost(host)
        self.delete()
        return username, password

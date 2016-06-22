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
from mcvirt.mcvirt_config import MCVirtConfig


class ClusterUser(UserBase):
    """User type for cluster daemon users"""

    USER_PREFIX = 'mcv-cluster-'
    CAN_GENERATE = True
    CLUSTER_USER = True

    @property
    def ALLOW_PROXY_USER(self):
        """Connection users can proxy for another user"""
        return True

    @staticmethod
    def getDefaultConfig():
        """Returns the default user config"""
        default_config = UserBase.getDefaultConfig()
        default_config['host'] = None
        return default_config

    def updateHost(self, host):
        """Updates the host associated with the user"""
        def updateConfig(config):
            config['users'][self.getUsername()]['host'] = host
        MCVirtConfig().updateConfig(updateConfig, 'Updated host for \'%s\'' % self.getUsername())

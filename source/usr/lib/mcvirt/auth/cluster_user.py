"""Provide class for managing cluster users."""

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

from mcvirt.auth.user_base import UserBase
from mcvirt.mcvirt_config import MCVirtConfig


class ClusterUser(UserBase):
    """User type for cluster daemon users."""

    USER_PREFIX = 'mcv-cluster-'
    CAN_GENERATE = True
    CLUSTER_USER = True
    DISTRIBUTED = False

    @property
    def allow_proxy_user(self):
        """Connection users can proxy for another user."""
        return True

    @staticmethod
    def get_default_config():
        """Return the default user config."""
        default_config = UserBase.get_default_config()
        default_config['host'] = None
        return default_config

    @property
    def node(self):
        """Return the node that the user is used for"""
        return self._get_config()['host']

    def update_host(self, host):
        """Update the host associated with the user."""
        def update_config(config):
            config['users'][self.get_username()]['host'] = host
        MCVirtConfig().update_config(update_config, 'Updated host for \'%s\'' %
                                                    self.get_username())

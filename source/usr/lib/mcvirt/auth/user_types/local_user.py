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

import Pyro4

from mcvirt.auth.user_types.user_base import UserBase
from mcvirt.auth.permissions import PERMISSIONS


class LocalUser(UserBase):
    """Provides an interaction with the local user backend"""

    @Pyro4.expose()
    def set_password(self, new_password):
        """Change the current user's password."""
        # Check that the current user is the same as this user, or that current user has the correct
        # permissions
        actual_user = self._get_registered_object('mcvirt_session').get_proxy_user_object()
        if actual_user.get_username() != self.get_username():
            self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)

        self._set_password(new_password)

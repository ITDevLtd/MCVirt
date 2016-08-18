"""Provide class for ldap users"""

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
from mcvirt.rpc.lock import locking_method


class LdapUser(UserBase):
    """Provides an interaction with ldap user backend"""

    CAN_CREATE = False

    @staticmethod
    def _check_exists(username):
        """Check the MCVirt config to determine if a given user exists."""
        pass

    def _get_config(self):
        """Return the config hash for the current user"""
        return {
            'user_type': self.__class__.__name__
        }

    def get_user_type(self):
        """Return the user type of the user"""
        return self.__class__.__name__

    def _check_password(self, password):
        """Check the given password against the stored password for the user."""
        pass

    def _get_password_salt(self):
        """Return the user's salt"""
        raise NotImplemented

    def _set_password(self, new_password):
        """Set the password for the current user"""
        raise NotImplemented

    @Pyro4.expose()
    @locking_method()
    def delete(self):
        """Delete the current user from MCVirt config"""
        raise NotImplemented

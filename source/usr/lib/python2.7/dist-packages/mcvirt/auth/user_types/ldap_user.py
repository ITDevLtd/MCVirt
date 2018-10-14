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

import ldap
import Pyro4

from mcvirt.auth.user_types.user_base import UserBase
from mcvirt.exceptions import MCVirtException, LdapConnectionFailedException
from mcvirt.node.ldap_factory import LdapFactory
from mcvirt.rpc.expose_method import Expose


class LdapUser(UserBase):
    """Provides an interaction with ldap user backend"""

    CAN_CREATE = False
    SEARCH_ORDER = 2
    LOCALLY_MANAGED = False

    @classmethod
    def get_all_usernames(cls):
        """Return all LDAP users."""
        return LdapFactory().get_all_usernames()

    def _get_dn(self):
        """Obtain the DN for the given user"""
        return self._get_registered_object('ldap_factory').search_dn(self.get_username())

    def _get_config(self):
        """Return the config hash for the current user"""
        # @TODO: Do we not store information about LDAP users?
        return {
            'user_type': self.__class__.__name__,
            'global_permissions': []
        }

    def get_user_type(self):
        """Return the user type of the user"""
        return self.__class__.__name__

    def _check_password(self, password):
        """Check the given password against the stored password for the user."""
        # If either username or password are empty strings or None, reject user.
        if not self.get_username() or not password:
            return False

        try:
            self._get_registered_object('ldap_factory').get_connection(bind_dn=self._get_dn(),
                                                                       password=password)
            return True
        except ldap.INVALID_CREDENTIALS:
            pass
        except MCVirtException:
            raise
        except:
            raise LdapConnectionFailedException('An error occurred whilst connecting to LDAP')
        return False

    def _get_password_salt(self):
        """Return the user's salt"""
        raise NotImplementedError

    def _set_password(self, new_password):
        """Set the password for the current user"""
        raise NotImplementedError

    @Expose(locking=True)
    def delete(self):
        """Delete the current user from MCVirt config"""
        raise NotImplementedError

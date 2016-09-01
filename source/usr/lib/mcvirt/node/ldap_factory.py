"""Provides interface to mange the LDAP interface."""

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
import ldap
import os

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import locking_method
from mcvirt.exceptions import (LdapConnectionFailedException, LdapNotEnabledException,
                               UserDoesNotExistException, UnknownLdapError)
from mcvirt.constants import DirectoryLocation


class LdapFactory(PyroObject):
    """Performs configuration of DRBD on the node"""

    CONNECTION = None
    UNCHANGED = object()

    @property
    def ldap_ca_cert_path(self):
        """Return the path for the LDAP CA certificate"""
        return '%s/ldap-ca.crt' % (DirectoryLocation.NODE_STORAGE_DIR)

    def get_connection(self, bind_dn=None, password=None):
        """Return an LDAP object"""

        if not LdapFactory.is_enabled():
            raise LdapNotEnabledException('Ldap has not been configured on this node')

        ca_cert_exists = os.path.exists(self.ldap_ca_cert_path)
        ldap_config = MCVirtConfig().get_config()['ldap']

        ldap.set_option(
            ldap.OPT_X_TLS_CACERTFILE,
            self.ldap_ca_cert_path if ca_cert_exists else ''
        )

        if bind_dn is None and password is None:
            bind_dn = ldap_config['bind_dn']
            password = ldap_config['bind_pass']

        try:
            ldap_connection = ldap.initialize(uri=ldap_config['server_uri'])
            try:
                ldap_connection.bind_s(bind_dn, password)
            except AttributeError:
                # This is required for the mockldap server as part of the unit tests
                ldap_connection.simple_bind_s(bind_dn, password)
        except:
            raise LdapConnectionFailedException(
                'Connection attempts to the LDAP server failed.'
            )

        return ldap_connection

    @staticmethod
    def is_enabled():
        """Determine if LDAP authentication is enabled"""
        return MCVirtConfig().get_config()['ldap']['enabled']

    @Pyro4.expose()
    @locking_method()
    def set_enable(self, enable):
        """Flag as to whether LDAP authentication
        is enabled or disabled.
        """
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)

        def update_config(config):
            config['ldap']['enabled'] = enable
        MCVirtConfig().update_config(update_config, 'Updated LDAP status')

        if self._is_cluster_master:
            def remote_command(node_connection):
                remote_ldap_factory = node_connection.get_connection('ldap_factory')
                remote_ldap_factory.set_enable(enable)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

    def get_user_filter(self, username=None):
        """Determine a search filter based on user filtering and custom search filter"""
        ldap_config = MCVirtConfig().get_config()['ldap']
        if username:
            username_filter = '(%s=%s)' % (ldap_config['username_attribute'], username)
        else:
            username_filter = None

        if ldap_config['user_search']:
            user_object_filter = ldap_config['user_search']
            if (not (user_object_filter.startswith('(') and
                     ldap_config['user_search'].endswith(')'))):
                user_object_filter = '(%s)' % user_object_filter
        else:
            user_object_filter = None

        if username_filter and user_object_filter:
            return '(&%s%s)' % (username_filter, user_object_filter)
        elif username_filter:
            return username_filter
        elif user_object_filter:
            return user_object_filter
        else:
            return '(%s=*)' % ldap_config['username_attribute']

    def get_all_usernames(self):
        """Return all users in the searchable LDAP directory"""
        if not LdapFactory.is_enabled():
            return []

        ldap_config = MCVirtConfig().get_config()['ldap']
        ldap_con = self.get_connection()

        try:
            res = ldap_con.search_s(ldap_config['base_dn'], ldap.SCOPE_SUBTREE,
                                    self.get_user_filter(),
                                    [str(ldap_config['username_attribute'])])
        except:
            raise UnknownLdapError(('An LDAP search error occurred. Please read the MCVirt'
                                    ' logs for more information'))
        return [user_obj[1][ldap_config['username_attribute']][0] for user_obj in res]

    def search_dn(self, username):
        """Determine a DN for a given username"""
        ldap_config = MCVirtConfig().get_config()['ldap']
        ldap_con = self.get_connection()

        try:
            res = ldap_con.search_s(str(ldap_config['base_dn']), ldap.SCOPE_SUBTREE,
                                    self.get_user_filter(username),
                                    [str(ldap_config['username_attribute'])])

        except:
            raise UnknownLdapError(('An LDAP search error occurred. Please read the MCVirt'
                                    ' logs for more information'))
        if len(res):
            return res[0][0]
        else:
            raise UserDoesNotExistException('User not returned by LDAP search')

    @Pyro4.expose()
    @locking_method()
    def set_config(self, server_uri=UNCHANGED, base_dn=UNCHANGED,
                   user_search=UNCHANGED, ca_cert=UNCHANGED,
                   bind_dn=UNCHANGED, bind_pass=UNCHANGED,
                   username_attribute=UNCHANGED):
        """Set config variables for the LDAP connection.
        Default value for each variable will leave the current set value.
        Setting values to None will set them to None in the config, as well as any passed
        string.
        """
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_USERS)
        config_changes = {}
        for config in ['server_uri', 'base_dn', 'user_search', 'bind_dn', 'bind_pass',
                       'username_attribute']:
            value = locals()[config]
            if value is not LdapFactory.UNCHANGED:
                config_changes[config] = value

        def update_config(config):
            config['ldap'].update(config_changes)
        MCVirtConfig().update_config(update_config, 'Updated LDAP configuration')

        # Update CA certificate if the user has updated it.
        if ca_cert is None:
            os.remove(self.ldap_ca_cert_path)
            config_changes['ca_cert'] = None
        elif ca_cert is not LdapFactory.UNCHANGED:
            with open(self.ldap_ca_cert_path, 'w') as ca_fh:
                ca_fh.write(ca_cert)
            config_changes['ca_cert'] = ca_cert

        if self._is_cluster_master:
            def remote_command(node_connection):
                remote_ldap_factory = node_connection.get_connection('ldap_factory')
                remote_ldap_factory.set_config(**config_changes)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

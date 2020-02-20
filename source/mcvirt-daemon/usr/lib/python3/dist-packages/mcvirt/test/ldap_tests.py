# pylint: disable=C0103
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

import unittest
import tempfile
import os
from mockldap import MockLdap

from mcvirt.test.test_base import TestBase
from mcvirt.parser import Parser
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.exceptions import AuthenticationError, ArgumentParserException
from mcvirt.constants import DirectoryLocation
from mcvirt.node.ldap_factory import LdapFactory


class LdapTests(TestBase):
    """Provides unit tests for LDAP authentication."""

    TEST_LDAP_CONFIG = {
        "bind_pass": "",
        "server_uri": "ldap://localhost",
        "base_dn": "ou=People,dc=example,dc=com",
        "enabled": True,
        "bind_dn": "",
        "user_search": None,
        "username_attribute": "uid"
    }

    TEST_USERS = [
        {'username': 'test-user1', 'password': 'test-password1'},
        {'username': 'test-user2', 'password': 'test-password2'}
    ]

    # Test Ldap directory
    user_base = ('ou=People,dc=example,dc=com', {'ou': ['People']})
    user_1 = ('uid=%s,ou=People,dc=example,dc=com' % TEST_USERS[0]['username'], {
        'uid': [TEST_USERS[0]['username']],
        'userPassword': [TEST_USERS[0]['password']],
        'loginShell': ['/bin/bash']
    })
    user_2 = ('uid=%s,ou=People,dc=example,dc=com' % TEST_USERS[1]['username'], {
        'uid': [TEST_USERS[1]['username']],
        'userPassword': [TEST_USERS[1]['password']],
        'loginShell': ['/usr/sbin/nologin']
    })
    DIRECTORY = dict([user_base, user_1, user_2])

    @classmethod
    def setUpClass(cls):
        """Setup class, creating mock ldap object."""
        super(cls, LdapTests).setUpClass()
        cls.mockldap = MockLdap(cls.DIRECTORY)

    @classmethod
    def tearDownClass(cls):
        """REmove mock ldap object."""
        del cls.mockldap
        super(cls, LdapTests).tearDownClass()

    def setUp(self):
        """Create test Ldap configuration."""
        super(LdapTests, self).setUp()

        # Keep a copy of the original Ldap config so it can be restored in the tear down
        self.original_ldap_config = MCVirtConfig().get_config()['ldap']

        def update_config(config):
            """Upate LDAP config in MCVirt config."""
            config['ldap'] = LdapTests.TEST_LDAP_CONFIG
        MCVirtConfig().update_config(update_config, 'Create test Ldap configuration')

        # Setup mock ldap
        self.mockldap.start()

        self.ldap_factory = LdapFactory()

    def tearDown(self):
        """Restore the correct Ldap configuration."""
        def reset_config(config):
            """Reset LDAP config in MCVirt config."""
            config['ldap'] = self.original_ldap_config
        MCVirtConfig().update_config(reset_config, 'Reset Ldap configuration')

        # Stop mock ldap
        self.mockldap.stop()

        super(LdapTests, self).tearDown()

    @staticmethod
    def suite():
        """Returns a test suite of the Ldap tests."""
        suite = unittest.TestSuite()
        suite.addTest(LdapTests('test_valid_user'))
        suite.addTest(LdapTests('test_invalid_user'))
        suite.addTest(LdapTests('test_parser'))
        suite.addTest(LdapTests('test_user_search'))
        return suite

    def run_test_command(self, username, password):
        """Run the list command with the provided credentials."""
        Parser(verbose=False).parse_arguments('list --username %s --password %s' %
                                              (username, password))

    def check_parser(self, command, option, expected_value):
        """Run the provided command and assert that the specified option in the Ldap config has
        changed to the appropriate value."""
        self.parser.parse_arguments(command)
        self.assertEqual(MCVirtConfig().get_config()['ldap'][option], expected_value)

    def test_parser(self):
        """Test the Ldap options work correctly in the parser."""
        self.check_parser('node --enable-ldap', 'enabled', True)
        self.check_parser('node --disable-ldap', 'enabled', False)

        self.check_parser('node --server-uri new-uri', 'server_uri', 'new-uri')
        self.check_parser('node --clear-server-uri', 'server_uri', None)

        self.check_parser('node --base-dn new-dn', 'base_dn', 'new-dn')
        self.check_parser('node --clear-base-dn', 'base_dn', None)

        self.check_parser('node --bind-dn new-bind-dn-here', 'bind_dn', 'new-bind-dn-here')
        self.check_parser('node --clear-bind-dn', 'bind_dn', None)

        self.check_parser('node --bind-pass bindpass123', 'bind_pass', 'bindpass123')
        self.check_parser('node --clear-bind-pass', 'bind_pass', None)

        self.check_parser('node --user-search myusersearch426', 'user_search', 'myusersearch426')
        self.check_parser('node --clear-user-search', 'user_search', None)

        self.check_parser('node --username-attribute usern4m3attribut3', 'username_attribute',
                          'usern4m3attribut3')
        self.check_parser('node --clear-username-attribute', 'username_attribute', None)

        # Remove existing CA cert file if it exists
        ca_cert_path = self.ldap_factory.ldap_ca_cert_path
        try:
            os.remove(ca_cert_path)
        except OSError:
            pass

        tmp = tempfile.NamedTemporaryFile()
        # Try adding CA cert file that does not exist
        with self.assertRaises(Exception):
            self.parser.parse_arguments('node --ca-cert-file %s' % (tmp.name + '1234'))
        # Add CA cert and check file is copied to correct location
        self.parser.parse_arguments('node --ca-cert-file %s' % tmp.name)
        self.assertTrue(os.path.exists(ca_cert_path))

    def test_valid_user(self):
        """Test running a command with valid Ldap credentials."""
        try:
            self.run_test_command(LdapTests.TEST_USERS[0]['username'],
                                  LdapTests.TEST_USERS[0]['password'])
        except AuthenticationError:
            self.fail('Valid Ldap credentials resulted in authentication failure')

    def test_invalid_user(self):
        """Test running a command with invalid Ldap credentials."""
        # Test using a valid username but invalid password
        with self.assertRaises(AuthenticationError):
            self.run_test_command(LdapTests.TEST_USERS[0]['username'], 'wrong-password')

        # Test using an invalid username
        with self.assertRaises(AuthenticationError):
            self.run_test_command('invalid-user', 'wrong-password')

    def test_user_search(self):
        """Test that getting LDAP usernames takes the user_search attribute into account."""
        def update_config(config):
            """Update LDAP config in MCVirt config."""
            config['ldap']['user_search'] = '(loginShell=/bin/bash)'
        MCVirtConfig().update_config(update_config, 'Set user_search')

        ldap_users = self.ldap_factory.get_all_usernames()
        self.assertTrue(LdapTests.TEST_USERS[0]['username'] in ldap_users)
        self.assertFalse(LdapTests.TEST_USERS[1]['username'] in ldap_users)

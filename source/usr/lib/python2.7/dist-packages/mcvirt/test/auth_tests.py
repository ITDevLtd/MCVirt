# Copyright (c) 2014 - I.T. Dev Ltd
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

from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.auth.auth import Auth
from mcvirt.exceptions import (InsufficientPermissionsException, AuthenticationError,
                               UserDoesNotExistException, DuplicatePermissionException,
                               ArgumentParserException, UserNotPresentInGroup)
from mcvirt.test.test_base import TestBase
from mcvirt.parser import Parser
from mcvirt.client.rpc import Connection


class AuthTests(TestBase):
    """Provides unit tests for the Auth class"""

    TEST_USERNAME = 'test-user'
    TEST_PASSWORD = 'test-password'
    TEST_USERNAME_ALTERNATIVE = 'user-to-delete'

    def create_test_user(self, username, password):
        """Create a test user, annotate the user object and return it"""
        # Ensure that user does not already exist:
        try:
            test_user = self.user_factory.get_user_by_username(username)
            self.rpc.annotate_object(test_user)
            test_user.delete()
        except UserDoesNotExistException:
            pass

        self.user_factory.create(username, password)
        new_user = self.user_factory.get_user_by_username(username)
        self.rpc.annotate_object(new_user)
        return new_user

    def parse_command(self, command, username, password):
        """Parse the specified command with the specified credentials"""
        Parser(verbose=False).parse_arguments('%s --username %s --password %s' %
                                              (command, username, password))

    def setUp(self):
        """Set up a test user"""
        super(AuthTests, self).setUp()

        self.auth = self.rpc.get_connection('auth')
        self.user_factory = self.rpc.get_connection('user_factory')
        self.test_user = self.create_test_user(self.TEST_USERNAME, self.TEST_PASSWORD)

    def tearDown(self):
        """Remove the test user"""
        # If test_remove_user_account() failed then a user called 'user-to-delete' may still exist
        test_user = None
        try:
            test_user = self.user_factory.get_user_by_username(self.TEST_USERNAME_ALTERNATIVE)
            self.rpc.annotate_object(test_user)
            test_user.delete()
        except UserDoesNotExistException:
            pass

        self.test_user.delete()
        self.test_user = None
        self.user_factory = None
        self.auth = None

        super(AuthTests, self).tearDown()

    @staticmethod
    def suite():
        """Returns a test suite of the Auth tests"""
        suite = unittest.TestSuite()
        suite.addTest(AuthTests('test_add_remove_user_vm_permission'))
        suite.addTest(AuthTests('test_add_remove_user_global_permission'))
        suite.addTest(AuthTests('test_add_delete_superuser'))
        suite.addTest(AuthTests('test_attempt_add_superuser_to_vm'))
        suite.addTest(AuthTests('test_add_duplicate_superuser'))
        suite.addTest(AuthTests('test_delete_non_existant_superuser'))
        suite.addTest(AuthTests('test_change_password'))
        suite.addTest(AuthTests('test_add_new_user'))
        suite.addTest(AuthTests('test_remove_user_account'))
        return suite

    def test_add_remove_user_vm_permission(self):
        """Permission permission tests using VM role"""
        self.test_add_remove_user_permission(global_permission=False)

    def test_add_remove_user_global_permission(self):
        """Permission permission tests using global role"""
        self.test_add_remove_user_permission(global_permission=True)

    def test_add_remove_user_permission(self, global_permission):
        """Add a user to a virtual machine, using the argument parser"""
        # Ensure VM does not exist
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        permission_string = '--global' if global_permission else test_vm_object.get_name()

        # Ensure user is not in 'user' group
        self.assertFalse(
            self.test_user.get_username() in
            self.auth.get_users_in_permission_group('user', test_vm_object)
        )

        # Assert that the test user cannot start the test VM
        with self.assertRaises(InsufficientPermissionsException):
            self.parse_command('start %s' % test_vm_object.get_name(),
                               self.TEST_USERNAME, self.TEST_PASSWORD)

        # Add user to 'user' group using parser
        self.parser.parse_arguments('permission --add-user %s %s' % (self.test_user.get_username(),
                                                                     permission_string))

        # Ensure VM exists
        self.assertTrue(
            self.test_user.get_username() in self.auth.get_users_in_permission_group(
                'user', test_vm_object if (not global_permission) else None)
        )

        # Ensure that user can now start the VM
        self.parse_command('start %s' % test_vm_object.get_name(),
                           self.TEST_USERNAME, self.TEST_PASSWORD)
        # Ensure that user can now start the VM
        self.parse_command('stop %s' % test_vm_object.get_name(),
                           self.TEST_USERNAME, self.TEST_PASSWORD)

        # Attempt to re-add user to group
        with self.assertRaises(DuplicatePermissionException):
            # Add user to 'user' group using parser
            self.parser.parse_arguments('permission --add-user %s %s' %
                                        (self.test_user.get_username(),
                                         permission_string))

        # Remove user to 'user' group using parser
        self.parser.parse_arguments('permission --delete-user %s %s' %
                                    (self.test_user.get_username(),
                                     permission_string))

        # Assert that user is no longer part of the group
        self.assertFalse(
            self.test_user.get_username() in self.auth.get_users_in_permission_group(
                'user', test_vm_object if (not global_permission) else None)
        )

        # Assert that the test user cannot stop the test VM
        with self.assertRaises(InsufficientPermissionsException):
            self.parse_command('start %s' % test_vm_object.get_name(),
                               username=self.TEST_USERNAME,
                               password=self.TEST_PASSWORD)

    def test_add_delete_superuser(self):
        """Add/delete a user to/from the superuser role"""
        # Assert that the user is not already a superuser
        self.assertFalse(
            self.TEST_USERNAME in
            self.RPC_DAEMON.DAEMON.registered_factories['auth'].get_superusers()
        )

        # Add the user to the superuser group using the argument parser
        self.parser.parse_arguments('permission --add-superuser %s --global' % self.TEST_USERNAME)

        # Ensure that the auth object asserts that the user is a superuser
        self.assertTrue(
            self.TEST_USERNAME in
            self.RPC_DAEMON.DAEMON.registered_factories['auth'].get_superusers()
        )
        rpc_connection = Connection(username=self.TEST_USERNAME, password=self.TEST_PASSWORD)
        test_auth = rpc_connection.get_connection('auth')
        self.assertTrue(test_auth.is_superuser())

        # Ensure that user can start a test VM and delete it
        test_vm = self.create_vm('TEST_VM_1', 'Local')
        self.parse_command('start %s' % test_vm.get_name(),
                           username=self.TEST_USERNAME,
                           password=self.TEST_PASSWORD)

        self.parse_command('stop %s' % test_vm.get_name(),
                           username=self.TEST_USERNAME,
                           password=self.TEST_PASSWORD)

        self.parse_command('delete --delete-data %s' % test_vm.get_name(),
                           username=self.TEST_USERNAME,
                           password=self.TEST_PASSWORD)

        # Delete the user from the superuser group using the argument parser
        self.parser.parse_arguments('permission --delete-superuser %s --global' %
                                    self.TEST_USERNAME)

        # Assert that the user is no longer considered a superuser
        self.assertFalse(test_auth.is_superuser())

        # Assert that the user no longer has access to the superuser permission
        self.assertFalse(test_auth.is_superuser())
        self.assertFalse(
            self.TEST_USERNAME in
            self.RPC_DAEMON.DAEMON.registered_factories['auth'].get_superusers()
        )

    def test_attempt_add_superuser_to_vm(self):
        """Attempts to add a user as a superuser to a VM"""
        test_vm_object = self.create_vm('TEST_VM_1', 'Local')

        with self.assertRaises(ArgumentParserException):
            self.parser.parse_arguments('permission --add-superuser %s %s' %
                                        (self.TEST_USERNAME, test_vm_object.get_name()))

    def test_add_duplicate_superuser(self):
        """Attempts to add a superuser twice"""
        # Add the user as a superuser
        self.auth.add_superuser(self.test_user)

        with self.assertRaises(DuplicatePermissionException):
            self.parser.parse_arguments('permission --add-superuser %s --global' %
                                        self.TEST_USERNAME)

    def test_delete_non_existant_superuser(self):
        """Attempts to remove a non-existent user from the superuser group"""
        with self.assertRaises(UserNotPresentInGroup):
            self.parser.parse_arguments('permission --delete-superuser %s --global' %
                                        self.TEST_USERNAME)

    def test_change_password(self):
        """Change the password of a user through the parser"""
        # Change the password of the test user
        new_password = 'new-password-here'
        self.parse_command('user change-password --new-password %s' % new_password,
                           self.TEST_USERNAME, self.TEST_PASSWORD)

        # Try to run a command with the old credentials and check an AuthenticationError is raised
        with self.assertRaises(AuthenticationError):
            self.parse_command('list', self.TEST_USERNAME, self.TEST_PASSWORD)

        # Now run a command as the test user with the new password
        try:
            self.parse_command('list', self.TEST_USERNAME, new_password)
        except AuthenticationError:
            self.fail('Password not changed successfully')

    def test_add_new_user(self):
        """Create a new user through the parser"""
        username = 'brand-new-user'
        password = 'pass'
        create_command = 'user create %s --user-password %s' % (username, password)

        # Try to create a new user as the test user and check an InsufficientPermissionsException
        # is raised
        with self.assertRaises(InsufficientPermissionsException):
            self.parse_command(create_command, self.TEST_USERNAME, self.TEST_PASSWORD)

        # Create the new user as a superuser
        self.parser.parse_arguments(create_command)

        # Check the new user exists
        try:
            new_user = self.user_factory.get_user_by_username(username)

            # Delete the new user
            self.rpc.annotate_object(new_user)
            new_user.delete()

        except UserDoesNotExistException:
            self.fail('User not created')

        # Create the new user again using the --generate-password flag
        self.parser.parse_arguments('user create %s --generate-password' % username)
        # Check the new user exists
        try:
            new_user = self.user_factory.get_user_by_username(username)

            # Delete the new user
            self.rpc.annotate_object(new_user)
            new_user.delete()

        except UserDoesNotExistException:
            self.fail('User not created')

    def test_remove_user_account(self):
        """Delete a user through the parser"""
        self.user_to_delete = self.create_test_user(self.TEST_USERNAME_ALTERNATIVE, 'pass')
        delete_command = 'user delete %s' % self.TEST_USERNAME_ALTERNATIVE

        # Try to delete as test user and check InsufficientPermissionsException is raised
        with self.assertRaises(InsufficientPermissionsException):
            self.parse_command(delete_command, self.TEST_USERNAME, self.TEST_PASSWORD)

        # Run delete command as superuser
        self.parser.parse_arguments(delete_command)

        # Check that the user no longer exists
        with self.assertRaises(UserDoesNotExistException):
            self.user_factory.get_user_by_username(self.TEST_USERNAME_ALTERNATIVE)

        self.user_to_delete = None

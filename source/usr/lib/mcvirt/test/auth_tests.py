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
                               UserDoesNotExistException)
from mcvirt.test.test_base import TestBase
from mcvirt.client.rpc import Connection
from mcvirt.parser import Parser


def removeTestUserPermissions(mcvirt_instance, username):
    """Removes the test user from all permission groups"""
    auth_object = mcvirt_instance.getAuthObject()

    try:
        auth_object.delete_user_permission_group(mcvirt_instance, 'user', username)
    except:
        pass
    try:
        auth_object.delete_user_permission_group(mcvirt_instance, 'user', username)
    except:
        pass
    try:
        auth_object.delete_superuser(username, mcvirt_instance)
    except:
        pass


class AuthTests(TestBase):
    """Provides unit tests for the Auth class"""

    TEST_USERNAME = 'test-user'
    TEST_PASSWORD = 'test-password'

    def create_test_user(self, username, password):
        """Create a test user, annotate the user object and return it"""
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

        self.user_factory = self.rpc.get_connection('user_factory')
        self.test_user = self.create_test_user(self.TEST_USERNAME, self.TEST_PASSWORD)

    def tearDown(self):
        """Remove the test user"""
        super(AuthTests, self).tearDown()
        self.test_user.delete()
        self.test_user = None

        # If test_remove_user_account() failed then a user called 'user-to-delete' may still exist
        if getattr(self, 'user_to_delete', None) is not None:
            self.user_to_delete.delete()

    @staticmethod
    def suite():
        """Returns a test suite of the Auth tests"""
        suite = unittest.TestSuite()
        # @TODO: update commented out tests
        # suite.addTest(AuthTests('test_add_user'))
        # suite.addTest(AuthTests('test_remove_user'))
        # suite.addTest(AuthTests('test_add_delete_superuser'))
        # suite.addTest(AuthTests('test_attempt_add_superuser_to_vm'))
        # suite.addTest(AuthTests('test_add_duplicate_superuser'))
        # suite.addTest(AuthTests('test_delete_non_existant_superuser'))
        suite.addTest(AuthTests('test_change_password'))
        suite.addTest(AuthTests('test_add_new_user'))
        suite.addTest(AuthTests('test_remove_user_account'))
        return suite

    def test_add_user(self):
        """Adds a user to a virtual machine, using the argument parser"""
        # Ensure VM does not exist
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vm['name'],
            self.test_vm['cpu_count'],
            self.test_vm['memory_allocation'],
            self.test_vm['disks'],
            self.test_vm['networks'])
        self.assertTrue(
            VirtualMachine._check_exists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vm['name']))

        # Ensure user is not in 'user' group
        self.assertFalse(
            self.test_user in self.auth_object.get_users_in_permission_group(
                'user',
                test_vm_object))

        # Add user to 'user' group using parser
        self.parser.parse_arguments(
            'permission --add-user %s %s' %
            (self.test_user,
             self.test_vm['name']),
            mcvirt_instance=self.mcvirt)

        # Ensure VM exists
        self.assertTrue(
            self.test_user in self.auth_object.get_users_in_permission_group(
                'user',
                test_vm_object))

    def test_remove_user(self):
        """Removes a user from a virtual machine, using the argument parser"""
        # Ensure VM does not exist
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vm['name'],
            self.test_vm['cpu_count'],
            self.test_vm['memory_allocation'],
            self.test_vm['disks'],
            self.test_vm['networks'])
        self.assertTrue(
            VirtualMachine._check_exists(
                self.mcvirt.getLibvirtConnection(),
                self.test_vm['name']))

        # Add user to 'user' group and ensure they have been added
        self.auth_object.add_user_permission_group(self.mcvirt, 'user', self.test_user,
                                                   test_vm_object)
        self.assertTrue(
            self.test_user in self.auth_object.get_users_in_permission_group(
                'user',
                test_vm_object))

        # Remove user from 'user' group using parser
        self.parser.parse_arguments(
            'permission --delete-user %s %s' %
            (self.test_user,
             self.test_vm['name']),
            mcvirt_instance=self.mcvirt)

        # Ensure user is no longer in 'user' group
        self.assertFalse(
            self.test_user in self.auth_object.get_users_in_permission_group(
                'user',
                test_vm_object
            ))

    def test_add_delete_superuser(self):
        """Adds/deletes a user to/from the superuser role"""
        # Assert that the user is not already a superuser
        self.assertFalse(self.test_auth_object.is_superuser())

        # Add the user to the superuser group using the argument parser
        self.parser.parse_arguments('permission --add-superuser %s --global' % self.test_user,
                                    mcvirt_instance=self.mcvirt)

        # Ensure that the auth object asserts that the user is a superuser
        self.assertTrue(self.test_auth_object.is_superuser())

        # Assert that the user has access to a superuser permission
        self.assertTrue(
            self.test_auth_object.assert_permission(Auth.PERMISSIONS.TEST_SUPERUSER_PERMISSION)
        )

        # Delete the user from the superuser group using the argument parser
        self.parser.parse_arguments('permission --delete-superuser %s --global' % self.test_user,
                                    mcvirt_instance=self.mcvirt)

        # Assert that the user is no longer considered a superuser
        self.assertFalse(self.test_auth_object.is_superuser())

        # Assert that the user no longer has access to the superuser permission
        with self.assertRaises(InsufficientPermissionsException):
            self.test_auth_object.assert_permission(Auth.PERMISSIONS.TEST_SUPERUSER_PERMISSION)

    def test_attempt_add_superuser_to_vm(self):
        """Attempts to add a user as a superuser to a VM"""
        test_vm_object = VirtualMachine.create(
            self.mcvirt,
            self.test_vm['name'],
            self.test_vm['cpu_count'],
            self.test_vm['memory_allocation'],
            self.test_vm['disks'],
            self.test_vm['networks']
        )

        with self.assertRaises(MCVirtException):
            self.parser.parse_arguments('permission --add-superuser %s %s' %
                                        (self.test_user, self.test_vm['name']),
                                        mcvirt_instance=self.mcvirt)

    def test_add_duplicate_superuser(self):
        """Attempts to add a superuser twice"""
        # Add the user as a superuser
        self.auth_object.add_superuser(self.test_user, self.mcvirt)

        with self.assertRaises(MCVirtException):
            self.parser.parse_arguments('permission --add-superuser %s --global' % self.test_user,
                                        mcvirt_instance=self.mcvirt)

    def test_delete_non_existant_superuser(self):
        """Attempts to remove a non-existent user from the superuser group"""
        with self.assertRaises(MCVirtException):
            self.parser.parse_arguments('permission --delete-superuser %s --global' %
                                        self.test_user,
                                        mcvirt_instance=self.mcvirt)

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
            self.fail('Password not changed succesfully')

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
        self.user_to_delete = self.create_test_user('user-to-delete', 'pass')
        delete_command = 'user remove user-to-delete'

        # Try to delete as test user and check InsufficientPermissionsException is raised
        with self.assertRaises(InsufficientPermissionsException):
            self.parse_command(delete_command, self.TEST_USERNAME, self.TEST_PASSWORD)

        # Run delete command as superuser
        self.parser.parse_arguments(delete_command)

        # Check that the user no longer exists
        with self.assertRaises(UserDoesNotExistException):
            self.user_factory.get_user_by_username('user-to-delete')

        self.user_to_delete = None

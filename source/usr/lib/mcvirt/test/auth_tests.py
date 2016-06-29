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

from mcvirt.parser import Parser
from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.auth.auth import Auth
from mcvirt.exceptions import InsufficientPermissionsException


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


class AuthTests(unittest.TestCase):
    """Provides unit tests for the Auth class"""

    @staticmethod
    def suite():
        """Returns a test suite of the Auth tests"""
        suite = unittest.TestSuite()
        suite.addTest(AuthTests('test_add_user'))
        suite.addTest(AuthTests('test_remove_user'))
        suite.addTest(AuthTests('test_add_delete_superuser'))
        suite.addTest(AuthTests('test_attempt_add_superuser_to_vm'))
        suite.addTest(AuthTests('test_add_duplicate_superuser'))
        suite.addTest(AuthTests('test_delete_non_existant_superuser'))
        return suite

    def setUp(self):
        """Creates various objects and deletes any test VMs"""
        # Create MCVirt parser object
        self.parser = Parser(print_status=False)

        # Get an MCVirt instance
        self.mcvirt = MCVirt()

        # Setup variable for test VM
        self.test_vm = \
            {
                'name': 'mcvirt-unittest-vm',
                'cpu_count': '1',
                'disks': ['100'],
                'memory_allocation': '100',
                'networks': ['Production']
            }

        self.test_user = 'test_user'
        self.test_auth_object = Auth(self.mcvirt, self.test_user)
        self.auth_object = Auth(self.mcvirt)

        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vm['name'])
        removeTestUserPermissions(self.mcvirt, self.test_user)

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vm['name'])
        removeTestUserPermissions(self.mcvirt, self.test_user)
        self.mcvirt = None

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

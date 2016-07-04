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

from mcvirt.exceptions import InvalidVirtualMachineNameException
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.test.test_base import TestBase


class ValidationTests(TestBase):
    """Provides unit tests for validation"""

    @staticmethod
    def suite():
        """Return a test suite of validation tests"""
        suite = unittest.TestSuite()
        suite.addTest(ValidationTests('test_create_vm'))
        suite.addTest(ValidationTests('test_create_network'))
        suite.addTest(ValidationTests('test_hostnames'))
        suite.addTest(ValidationTests('test_network_names'))
        suite.addTest(ValidationTests('test_integer'))
        suite.addTest(ValidationTests('test_pos_integer'))
        suite.addTest(ValidationTests('test_boolean'))
        suite.addTest(ValidationTests('test_drbd_resource'))
        return suite

    def test_validity(self, validator, valid_list, invalid_list, expected_exception=TypeError):
        """Use the provided validator function to test each string in valid_list and invalid_list,
        failing the test if expected_exception is raised for anything in valid_list, and failing
        if the exception is NOT raised for anything in invalid_list"""
        for i in valid_list:
            try:
                validator(i)
            except expected_exception:
                self.fail('%s was incorrectly raised for \'%s\' in %s' %
                          (expected_exception.__name__, i, validator.__name__))

        for i in invalid_list:
            # Catch the AssertionError here to give a more meaningful message
            try:
                with self.assertRaises(expected_exception):
                    validator(i)
            except AssertionError:
                raise AssertionError('%s not raised for \'%s\' in %s' %
                                     (expected_exception.__name__, i, validator.__name__))

    def test_create_vm(self):
        """Test an invalid VM name to check that VM creation uses ArgumentValidator"""
        with self.assertRaises(InvalidVirtualMachineNameException):
            self.parser.parse_arguments('create --memory %s --cpu-count %s -- %s' %
                                        (self.test_vms['TEST_VM_1']['memory_allocation'],
                                         self.test_vms['TEST_VM_1']['cpu_count'],
                                         '-startingWithADash'))

    def test_create_network(self):
        """Test creating a netork with an invalid name to check that network creation uses
        ArgumentValidator"""
        network_name = 'not-valid'
        try:
            with self.assertRaises(TypeError):
                self.parser.parse_arguments('network create --interface %s %s' %
                                            (self.test_physical_interface, network_name))
        except AssertionError as e:
            # If no TypeError was raised then the network was probably created succesfully, so need
            # to remove it
            if self.network_factory.check_exists(network_name):
                network = self.network_factory.get_network_by_name(network_name)
                self.rpc.annotate_object(network)
                network.delete()

            raise e

    def test_hostnames(self):
        """Test the validation of hostnames"""
        valid = ['validname', 'with123numbers', 'with-dashes', '1validname', 'x' * 63, 'x' * 64]
        invalid = ['-StartingWithADash', 'EndingWithADash-', 'name!#', 'x' * 65]
        self.test_validity(ArgumentValidator.validate_hostname, valid, invalid)

    def test_network_names(self):
        """Test the validation of network names"""
        valid = ['normalName', 'withNumbers999', '123456', 'x' * 63, 'x' * 64]
        invalid = ['not-very-valid', '!!!$$', 'x' * 65]
        self.test_validity(ArgumentValidator.validate_network_name, valid, invalid)

    def test_integer(self):
        """Test the validation of integers"""
        valid = [0, 1, '2', -4, '-10']
        invalid = ['hello', None, False, '4.5', 3.12, {}, []]
        self.test_validity(ArgumentValidator.validate_integer, valid, invalid)

    def test_pos_integer(self):
        """Test the validation of positive integers"""
        valid = [1, 2, 10, '99999999']
        invalid = [None, True, '-123', -234, 0]
        self.test_validity(ArgumentValidator.validate_positive_integer, valid, invalid)

    def test_boolean(self):
        """Test the validation of booleans"""
        valid = [True, False]
        invalid = ['True', None, 0, 1, '0']
        self.test_validity(ArgumentValidator.validate_boolean, valid, invalid)

    def test_drbd_resource(self):
        valid = ['mcvirt_vm-blah-disk-32', 'mcvirt_vm-test-disk-1', 'mcvirt_vm-blah-disk-99']
        invalid = ['xmcvirt_vm-blah-disk-1', 'mcvirt_vm-blah-disk-', 'MCVirt_vm-blah-disk-2',
                   'mcvirt_vm-blah-disk-2x', 'mcvirt_vm--disk-1', 'mcvirt_vm-test-disk-0',
                   'mcvirt_vm-blah-disk-100']
        self.test_validity(ArgumentValidator.validate_drbd_resource, valid, invalid)

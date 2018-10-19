# Copyright (c) 2018 - I.T. Dev Ltd
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

from mcvirt.test.test_base import TestBase
from mcvirt.size_converter import SizeConverter


class SizeConverterTests(TestBase):
    """Provides unit tests for LDAP authentication"""

    @staticmethod
    def suite():
        """Returns a test suite of the size converter tests"""
        suite = unittest.TestSuite()
        suite.addTest(SizeConverterTests('test_valid_bytes_int_without_units'))
        suite.addTest(SizeConverterTests('test_valid_bytes_str_without_units'))
        suite.addTest(SizeConverterTests('test_invalid_bytes_int_with_units_decimal'))
        suite.addTest(SizeConverterTests('test_valid_bytes_int_with_units_small'))
        suite.addTest(SizeConverterTests('test_valid_bytes_int_without_units_storage'))
        suite.addTest(SizeConverterTests('test_valid_bytes_str_without_units_storage'))
        suite.addTest(SizeConverterTests('test_invalid_bytes_int_with_units_decimal_storage'))
        suite.addTest(SizeConverterTests('test_invalid_bytes_int_with_units_small_storage'))
        return suite

    def test_valid_bytes_int_without_units(self):
        """Test passing valid size in bytes without units as integer"""
        size_obj = SizeConverter(105020)
        self.assertEqual(size_obj.to_bytes(), 105020)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_str_without_units(self):
        """Test passing valid size in bytes without units as string"""
        size_obj = SizeConverter('49218')
        self.assertEqual(size_obj.to_bytes(), 49218)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_invalid_bytes_int_with_units_decimal(self):
        """Test passing invalid decimal size in bytes without units as integer"""
        # Assert that an excpetion is raised
        with self.assertRaises(Exception):
            SizeConverter(523.53)

    def test_valid_bytes_int_with_units_small(self):
        """Test passing valid small size in bytes without units"""
        size_obj = SizeConverter(25)
        self.assertEqual(size_obj.to_bytes(), 25)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_int_without_units_storage(self):
        """Test passing valid size in bytes without units as integer as storage"""
        size_obj = SizeConverter(105020, storage=True)
        self.assertEqual(size_obj.to_bytes(), 105020)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_str_without_units_storage(self):
        """Test passing valid size in bytes without units as string as storage"""
        size_obj = SizeConverter('49218', storage=True)
        self.assertEqual(size_obj.to_bytes(), 49218)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_invalid_bytes_int_with_units_decimal_storage(self):
        """Test passing invalid decimal size in bytes without units as integer as storage"""
        # Assert that an excpetion is raised
        with self.assertRaises(Exception):
            SizeConverter(523.53, storage=True)

    def test_invalid_bytes_int_with_units_small_storage(self):
        """Test passing valid small size in bytes without units as storage"""
        with self.assertRaises(Exception):
            SizeConverter(25)

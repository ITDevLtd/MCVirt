# pylint: disable=C0103
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
from mcvirt.exceptions import (SizeMustBeMultipleOf512Error,
                               InvalidSizeSuffixError,
                               InvalidSizeFormatError,
                               SizeNotIntegerBytesError)


class SizeConverterTests(TestBase):
    """Provides unit tests for LDAP authentication"""

    @staticmethod
    def suite():
        """Returns a test suite of the size converter tests"""
        suite = unittest.TestSuite()
        suite.addTest(SizeConverterTests('test_valid_bytes_int_without_units'))
        suite.addTest(SizeConverterTests('test_valid_bytes_str_without_units'))
        suite.addTest(SizeConverterTests('test_invalid_bytes_int_with_units_decimal'))
        suite.addTest(SizeConverterTests('test_valid_bytes_int_with_units_non_512_multiple'))
        suite.addTest(SizeConverterTests('test_valid_bytes_int_without_units_storage'))
        suite.addTest(SizeConverterTests('test_valid_bytes_str_without_units_storage'))
        suite.addTest(SizeConverterTests('test_invalid_bytes_int_with_units_decimal_storage'))
        suite.addTest(SizeConverterTests('test_invalid_mb_str_with_units_decimal'))
        suite.addTest(SizeConverterTests('test_invalid_mb_str_with_units_decimal_storage'))
        suite.addTest(SizeConverterTests(
            'test_invalid_bytes_int_with_units_non_512_multiple_storage'))
        suite.addTest(SizeConverterTests('test_conversion_bytes'))
        suite.addTest(SizeConverterTests('test_conversion_kb'))
        suite.addTest(SizeConverterTests('test_conversion_kib'))
        suite.addTest(SizeConverterTests('test_conversion_mb'))
        suite.addTest(SizeConverterTests('test_conversion_mib'))
        suite.addTest(SizeConverterTests('test_conversion_gb'))
        suite.addTest(SizeConverterTests('test_conversion_gib'))
        suite.addTest(SizeConverterTests('test_conversion_tb'))
        suite.addTest(SizeConverterTests('test_conversion_tib'))
        suite.addTest(SizeConverterTests('test_conversion_mb_1dp'))
        suite.addTest(SizeConverterTests('test_conversion_mb_2dp'))
        suite.addTest(SizeConverterTests('test_conversion_mb_3dp'))
        suite.addTest(SizeConverterTests('test_conversion_mb_4dp'))
        suite.addTest(SizeConverterTests('test_conversion_mb_5dp'))
        suite.addTest(SizeConverterTests('test_conversion_mb_6dp'))
        suite.addTest(SizeConverterTests('test_conversion_invalid_case'))
        suite.addTest(SizeConverterTests('test_conversion_invalid_mb_storage_non_512'))
        suite.addTest(SizeConverterTests('test_conversion_b_to_tb'))
        suite.addTest(SizeConverterTests('test_invalid_size'))
        suite.addTest(SizeConverterTests('test_conversion_size_decimal_0dp'))

        return suite

    def test_valid_bytes_int_without_units(self):
        """Test passing valid size in bytes without units as integer"""
        size_obj = SizeConverter.from_string(43520)
        self.assertEqual(size_obj.to_bytes(), 43520)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_str_without_units(self):
        """Test passing valid size in bytes without units as string"""
        size_obj = SizeConverter.from_string('5632')
        self.assertEqual(size_obj.to_bytes(), 5632)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_invalid_bytes_int_with_units_decimal(self):
        """Test passing invalid decimal size in bytes without units as integer"""
        # Assert that an excpetion is raised
        with self.assertRaises(SizeNotIntegerBytesError):
            SizeConverter.from_string(523.53)

    def test_valid_bytes_int_with_units_non_512_multiple(self):
        """Test passing valid small size in bytes without units"""
        size_obj = SizeConverter.from_string(25)
        self.assertEqual(size_obj.to_bytes(), 25)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_int_without_units_storage(self):
        """Test passing valid size in bytes without units as integer as storage"""
        size_obj = SizeConverter.from_string(43520, storage=True)
        self.assertEqual(size_obj.to_bytes(), 43520)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_valid_bytes_str_without_units_storage(self):
        """Test passing valid size in bytes without units as string as storage"""
        size_obj = SizeConverter.from_string('11776', storage=True)
        self.assertEqual(size_obj.to_bytes(), 11776)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_invalid_bytes_int_with_units_decimal_storage(self):
        """Test passing invalid decimal size in bytes without units as integer as storage"""
        # Assert that an excpetion is raised
        with self.assertRaises(SizeNotIntegerBytesError):
            SizeConverter.from_string(523.53, storage=True)

    def test_invalid_mb_str_with_units_decimal(self):
        """Test passing invalid size that results in decimal bytes as sring"""
        # Assert that an excpetion is raised
        with self.assertRaises(SizeNotIntegerBytesError):
            SizeConverter.from_string('1.5231kB')

    def test_invalid_mb_str_with_units_decimal_storage(self):
        """Test passing invalid size that results in decimal bytes as sring as storage"""
        # Assert that an excpetion is raised
        with self.assertRaises(SizeNotIntegerBytesError):
            SizeConverter.from_string('1.5231kB', storage=True)

    def test_invalid_bytes_int_with_units_non_512_multiple_storage(self):
        """Test passing valid small size in bytes without units as storage"""
        with self.assertRaises(SizeMustBeMultipleOf512Error):
            SizeConverter.from_string(1023, storage=True)

    def test_conversion_bytes(self):
        """Test conversion of bytes"""
        size_obj = SizeConverter.from_string('131B')
        self.assertEqual(size_obj.to_bytes(), 131)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_kb(self):
        """Test conversion of MB"""
        size_obj = SizeConverter.from_string('535kB')
        self.assertEqual(size_obj.to_bytes(), 535000)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_kib(self):
        """Test conversion of KiB"""
        size_obj = SizeConverter.from_string('63KiB')
        self.assertEqual(size_obj.to_bytes(), 64512)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb(self):
        """Test conversion of MB"""
        size_obj = SizeConverter.from_string('124MB')
        self.assertEqual(size_obj.to_bytes(), 124000000)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mib(self):
        """Test conversion of MiB"""
        size_obj = SizeConverter.from_string('42MiB')
        self.assertEqual(size_obj.to_bytes(), 44040192)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_gb(self):
        """Test conversion of GB"""
        size_obj = SizeConverter.from_string('65GB')
        self.assertEqual(size_obj.to_bytes(), 65000000000)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_gib(self):
        """Test conversion of GiB"""
        size_obj = SizeConverter.from_string('21GiB')
        self.assertEqual(size_obj.to_bytes(), 22548578304)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_tb(self):
        """Test conversion of TB"""
        size_obj = SizeConverter.from_string('3TB')
        self.assertEqual(size_obj.to_bytes(), 3000000000000)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_tib(self):
        """Test conversion of TiB"""
        size_obj = SizeConverter.from_string('21TiB')
        self.assertEqual(size_obj.to_bytes(), 23089744183296)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_1dp(self):
        """Test conversion of MB with 1 decimal place"""
        size_obj = SizeConverter.from_string('535.5MB')
        self.assertEqual(size_obj.to_bytes(), 535500000)
        self.assertEqual(size_obj.to_string(), '535.5MB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_2dp(self):
        """Test conversion of MB with 2 decimal place"""
        size_obj = SizeConverter.from_string('535.45MB')
        self.assertEqual(size_obj.to_bytes(), 535450000)
        self.assertEqual(size_obj.to_string(), '535.45MB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_3dp(self):
        """Test conversion of MB with 3 decimal place"""
        size_obj = SizeConverter.from_string('535.501MB')
        self.assertEqual(size_obj.to_bytes(), 535501000)
        self.assertEqual(size_obj.to_string(), '535501kB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_4dp(self):
        """Test conversion of MB with 4 decimal place"""
        size_obj = SizeConverter.from_string('535.5519MB')
        self.assertEqual(size_obj.to_bytes(), 535551900)
        self.assertEqual(size_obj.to_string(), '535551.9kB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_5dp(self):
        """Test conversion of MB with 5 decimal place"""
        size_obj = SizeConverter.from_string('535.55192MB')
        self.assertEqual(size_obj.to_bytes(), 535551920)
        self.assertEqual(size_obj.to_string(), '535551.92kB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_mb_6dp(self):
        """Test conversion of MB with 6 decimal place"""
        size_obj = SizeConverter.from_string('535.551964MB')
        self.assertEqual(size_obj.to_bytes(), 535551964)
        self.assertEqual(size_obj.to_string(), '535551964B')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_invalid_case(self):
        """Test conversion of invalid suffix case"""
        size_obj = SizeConverter.from_string('11mIb')
        self.assertEqual(size_obj.to_bytes(), 11534336)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_conversion_invalid_mb_storage_non_512(self):
        """Test conversion of terrabytes for storage that is
        not a multiple of 512
        """
        with self.assertRaises(SizeMustBeMultipleOf512Error):
            SizeConverter.from_string('1.2MB', storage=True)

    def test_conversion_b_to_tb(self):
        """Test conversion of invalid suffix case"""
        size_obj = SizeConverter.from_string('3000000000000B')
        self.assertEqual(size_obj.to_bytes(), 3000000000000)
        self.assertEqual(size_obj.to_string(), '3TB')

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

    def test_invalid_size(self):
        """Test conversion of invalid size"""
        with self.assertRaises(InvalidSizeFormatError):
            SizeConverter.from_string('shouldnotwork')

    def test_conversion_size_decimal_0dp(self):
        """Test conversion of invalid size"""
        size_obj = SizeConverter.from_string('1.KiB')
        self.assertEqual(size_obj.to_bytes(), 1024)

        # Assert that bytes returned is an integer
        self.assertEqual(type(size_obj.to_bytes()), int)

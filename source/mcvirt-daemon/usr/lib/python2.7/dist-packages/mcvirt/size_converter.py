"""Module for sizes"""
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

from decimal import Decimal
import re


class Unit(object):
    """A unit object, which stores information about
    a single SI unit
    """

    def __init__(self, suffix, long_name, oom, dec):
        """Store member variables"""
        self.suffix = suffix
        self.long_name = long_name
        # Order of magnitude
        self.oom = oom

        # Decimal (boolean) (vs binary)
        self.dec = dec
        SizeConverter.units.append(self)

    def get_multiplier(self):
        """Get multiplier for unit"""
        base = 1000 if self.dec else 1024
        return base ** self.oom


class SizeConverter(object):
    """Convert string into object and provide methods to obtain
    the size in different formats
    """

    units = []

    def __init__(self, size, storage=False):
        """Create object and store size"""
        self.size = int(size)
        self.storage = storage

        # Ensure if if storage, the value must be a multiple of 512
        if storage and self.size % 512 != 0:
            raise Exception('Size must be a multiple of 512 bytes')

    @classmethod
    def get_units(cls):
        """Return the unit objects"""
        return cls.units

    @classmethod
    def from_string(cls, size_string, storage=False):
        """Create object from a string"""
        # Split value and units
        re_match = re.match(r'([0-9\.]+)([a-zA-Z]*)', str(size_string))
        if not re_match:
            return None
        size_s = re_match.group(1)
        unit_str = re_match.group(2) or 'B'
        if unit_str.lower() == 'b':
            size = size_s
        else:
            # Obtain unit type
            unit = [u for u in cls.units if u.suffix.lower() == unit_str.lower()]
            if not unit:
                raise Exception('Invalid unit suffix')
            unit = unit[0]
            # Convert size to bytes and create SizeConverter object
            size = Decimal(size_s) * unit.get_multiplier()

        # Ensure that value is a round number of bytes
        if str(int(size)) != str(size):
            raise Exception('Value not a round number of bytes')

        # Create size object, using integer of size
        return SizeConverter(int(size), storage=storage)

    def to_bytes(self):
        """Get size in bytes"""
        return self.size

    def to_string(self):
        """Convert to string"""
        # Iterate through units, from largest to smallest
        for unit in sorted(SizeConverter.units, key=lambda x: x.get_multiplier(), reverse=True):
            # If the value can be shown acurately to 2DP, then use this
            # for the string.. e.g. 1.25KB would return 1.25KB,
            # 1.001KB would return 1001B
            if (float(self.to_bytes()) / unit.get_multiplier() ==
                    round(float(self.to_bytes()) / unit.get_multiplier(), 2)):
                return '%s%s' % ((Decimal(self.to_bytes()) / unit.get_multiplier()), unit.suffix)


# Register units to be used
Unit('B', long_name='byte', oom=0, dec=True)
Unit('kB', long_name='kilobyte', oom=1, dec=True)
Unit('MB', long_name='megabyte', oom=2, dec=True)
Unit('GB', long_name='gigabyte', oom=3, dec=True)
Unit('TB', long_name='terabyte', oom=4, dec=True)
Unit('KiB', long_name='kibibyte', oom=1, dec=False)
Unit('MiB', long_name='mebibyte', oom=2, dec=False)
Unit('GiB', long_name='gibibyte', oom=3, dec=False)
Unit('TiB', long_name='tebibyte', oom=4, dec=False)

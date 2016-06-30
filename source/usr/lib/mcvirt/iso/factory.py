"""Provide factory class for ISO"""

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
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/

import os
import urllib2
import urlparse
import tempfile
import shutil
import binascii
import Pyro4

from mcvirt.iso.iso import Iso
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import locking_method
from mcvirt.constants import DirectoryLocation
from mcvirt.exceptions import InvalidISOPathException


class Factory(PyroObject):
    """Class for obtaining ISO objects"""

    ISO_CLASS = Iso

    def get_isos(self):
        """Return a list of a ISOs"""
        # Get files in ISO directory
        file_list = os.listdir(DirectoryLocation.ISO_STORAGE_DIR)
        iso_list = []

        for iso_name in file_list:
            iso_path = os.path.join(DirectoryLocation.ISO_STORAGE_DIR, iso_name)
            if os.path.isfile(iso_path):
                iso_list.append(iso_name)
        return iso_list

    @Pyro4.expose()
    def get_iso_by_name(self, iso_name):
        """Create and register Iso object"""
        iso_object = Iso(iso_name)
        self._register_object(iso_object)
        return iso_object

    @Pyro4.expose()
    def get_iso_list(self):
        """Return a user-readable list of ISOs"""
        iso_list = self.get_isos()
        if len(iso_list) == 0:
            return 'No ISOs found'
        else:
            return "\n".join(iso_list)

    def add_iso(self, path):
        """Copy an ISO to ISOs directory"""
        # Check that file exists
        if not os.path.isfile(path):
            raise InvalidISOPathException('Error: \'%s\' is not a file or does not exist' % path)

        filename = Iso.get_filename_from_path(path)
        Iso.overwrite_check(filename, DirectoryLocation.ISO_STORAGE_DIR + '/' + filename)

        shutil.copy(path, DirectoryLocation.ISO_STORAGE_DIR)

        return self.get_iso_by_name(filename)

    @Pyro4.expose()
    @locking_method()
    def add_from_url(self, url, name=None):
        """Download an ISO from given URL and save in ISO directory"""
        # Work out name from URL if name is not supplied
        if name is None:
            # Parse URL to get path part
            url_parse = urlparse.urlparse(url)
            name = Iso.get_filename_from_path(url_parse.path)

        # Get temporary directory to store ISO
        temp_directory = tempfile.mkdtemp()
        output_path = temp_directory + '/' + name

        # Open file
        iso = urllib2.urlopen(url)

        # Read file in 16KB chunks
        chunk_size = 16 * 1024

        # Save ISO
        with open(output_path, 'wb') as file:
            while True:
                chunk = iso.read(chunk_size)
                if not chunk:
                    break
                file.write(chunk)
        iso.close()

        iso_object = self.add_iso(output_path)

        os.remove(output_path)
        os.rmdir(temp_directory)
        return iso_object

    @Pyro4.expose()
    @locking_method()
    def add_iso_from_stream(self, path, name=None):
        """Import ISO, writing binary data to the ISO file"""
        if name is None:
            name = Iso.get_filename_from_path(path)

        # Get temporary directory to store ISO
        temp_directory = tempfile.mkdtemp()
        output_path = temp_directory + '/' + name

        iso_writer = IsoWriter(output_path, self, temp_directory, path)
        self._register_object(iso_writer)
        return iso_writer


class IsoWriter(PyroObject):
    """Provide an interface for writing ISOs"""

    def __init__(self, temp_file, factory, temp_directory, path):
        """Set methods to be able to create ISO from temp path."""
        self.temp_file = temp_file
        self.temp_directory = temp_directory
        self.factory = factory
        self.path = path
        self.fh = open(self.temp_file, 'wb')

    def __delete__(self):
        """Close FH on object deletion"""
        if self.fh:
            self.fh.close()
            self.fh = None

    @Pyro4.expose()
    def write_data(self, data):
        """Write data to the ISO file"""
        self.fh.write(binascii.unhexlify(data))

    @Pyro4.expose()
    def write_end(self):
        """End writing object, close FH and import ISO"""
        if self.fh:
            self.fh.close()
            self.fh = None

        iso_object = self.factory.add_iso(self.temp_file)

        os.remove(self.temp_file)
        os.rmdir(self.temp_directory)
        return iso_object

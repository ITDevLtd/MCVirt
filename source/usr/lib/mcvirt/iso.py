# Copyright (c) 2015 - I.T. Dev Ltd
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

import os
import stat

from mcvirt import MCVirtException
from system import System


class InvalidISOPathException(MCVirtException):
    """ISO to add does not exist"""
    pass


class NameNotSpecifiedException(MCVirtException):
    """A name has not been specified and cannot be determined by the path/URL"""
    pass


class IsoAlreadyExistsException(MCVirtException):
    """An ISO with the same name already exists"""
    pass


class FailedToRemoveFileException(MCVirtException):
    """A failure occurred whilst trying to remove an ISO"""
    pass


class IsoInUseException(MCVirtException):
    """The ISO is in use, so cannot be removed"""
    pass


class Iso:
    """Provides management of ISOs for use in MCVirt"""

    def __init__(self, mcvirt_instance, name):
        self.name = name
        self.mcvirt_instance = mcvirt_instance

        if (not os.path.isfile(self.getPath())):
            raise InvalidISOPathException('Error: \'%s\' does not exist' % self.getName())

        self.setIsoPermissions()

    def getName(self):
        return self.name

    def getPath(self):
        return self.mcvirt_instance.ISO_STORAGE_DIR + '/' + self.getName()

    @staticmethod
    def addFromUrl(mcvirt_instance, url, name=None):
        """Download an ISO from given URL and save in ISO directory"""
        import urllib2
        import urlparse
        import tempfile

        # Work out name from URL if name is not supplied
        if (name is None):
            # Parse URL to get path part
            url_parse = urlparse.urlparse(url)
            name = Iso.getFilenameFromPath(url_parse.path)

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

        iso_object = Iso.addIso(mcvirt_instance, output_path)

        os.remove(output_path)
        os.rmdir(temp_directory)

        return iso_object

    @staticmethod
    def addIso(mcvirt_instance, path):
        """Copy an ISO to ISOs directory"""
        import shutil

        # Check that file exists
        if (not os.path.isfile(path)):
            raise InvalidISOPathException('Error: \'%s\' is not a file or does not exist' % path)

        filename = Iso.getFilenameFromPath(path)
        Iso.overwriteCheck(mcvirt_instance, filename, mcvirt_instance.ISO_STORAGE_DIR + '/' + filename)

        shutil.copy(path, mcvirt_instance.ISO_STORAGE_DIR)
        full_path = mcvirt_instance.ISO_STORAGE_DIR + '/' + filename
        

        return 'ISO added successfully'

    @staticmethod
    def getFilenameFromPath(path, append_iso=True):
        """Return filename part of path"""
        filename = path.split('/')[-1]
        if (not filename):
            raise NameNotSpecifiedException('Name cannot be determined from "%s".' % path + "\n" +
                                            'Name parameter must be provided')
        if (filename[-4:].lower() != '.iso' and append_iso):
            filename += '.iso'

        return filename

    def setIsoPermissions(self):
        """Set permissions to 644"""
        mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(self.getPath(), mode)

    @staticmethod
    def overwriteCheck(mcvirt_instance, filename, path):
        """Check if a file already exists at path.
           Ask user whether they want to overwrite.
           Returns True if they will overwrite, False otherwise"""

        if (os.path.exists(path)):
            # If there is ask user if they want to overwrite
            overwrite_answer = System.getUserInput(
                '%s already exists, do you want to overwrite it? (Y/n): ' % Iso.getFilenameFromPath(path))
            if (overwrite_answer.strip() is not 'Y'):
                raise IsoAlreadyExistsException(
                    'Error: An ISO with the same name already exists: "%s"' % path
                )
            else:
                original_object = Iso(mcvirt_instance, filename)
                if (original_object.inUse()):
                    IsoInUseException('The original ISO is attached to a VM, so cannot be replaced')

        return True

    @staticmethod
    def getIsoList(mcvirt_instance):
        """Return a list of ISOs"""

        list = ''
        # Get files in ISO directory
        listing = os.listdir(mcvirt_instance.ISO_STORAGE_DIR)
        for file in listing:
            # If is a file and ends in '.iso' ...
            if (os.path.isfile(mcvirt_instance.ISO_STORAGE_DIR + '/' + file)):
                if len(list) > 0:
                    list += '\n'
                list += file

        if (len(list) == 0):
            list = 'No ISO found'

        return list

    def delete(self):
        """Delete an ISO"""
        # Check exists
        in_use = self.inUse()
        if (in_use):
            raise IsoInUseException(
                'The ISO is attached to a VM, so cannot be removed: %s' % in_use
            )

        delete_answer = System.getUserInput(
            'Are you sure you want to delete %s? (Y/n): ' % self.getName()
        )
        if (delete_answer.strip() is 'Y'):
            if (os.remove(self.getPath())):
                return True
            else:
                raise FailedToRemoveFileException(
                    'A failure occurred whilst attempting to remove ISO: %s' % self.getName()
                )
        else:
            return False

    def inUse(self):
        """Determines if the ISO is currently in use by a VM"""
        from virtual_machine.disk_drive import DiskDrive
        for vm_object in self.mcvirt_instance.getAllVirtualMachineObjects():
            vm_current_iso = DiskDrive(vm_object).getCurrentDisk()

            # If the VM has an iso attached, check if the ISO is this one
            if (vm_current_iso and (vm_current_iso.getPath() == self.getPath())):
                return vm_object.getName()

        return False


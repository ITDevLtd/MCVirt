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


class NotAnISOException(MCVirtException):
    """The ISO to add does not end in .iso, so assume it is not an ISO"""
    pass


class NameNotSpecifiedException(MCVirtException):
    """A name has not been specified and cannot be determined by the path/URL"""
    pass


class IsoAlreadyExistsException(MCVirtException):
    """An ISO with the same name already exists"""
    pass


class Iso:
    """Provides management of ISOs for use in MCVirt"""

    @staticmethod
    def addFromUrl(mcvirt_instance, url, name=None):
        """Download an ISO from given URL and save in ISO directory"""
        import urllib2
        import urlparse

        # Work out name from URL if name is not supplied
        if (name is None):
            # Parse URL to get path part
            url_parse = urlparse.urlparse(url)
            name = Iso.getFilenameFromPath(url_parse.path)

        if (not Iso.checkName(name)):
            name += '.iso'

        output_path = mcvirt_instance.ISO_STORAGE_DIR + '/' + name
        Iso.overwriteCheck(output_path)

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

        Iso.setIsoPermissions(output_path)

        return 'ISO downloaded as %s' % name

    @staticmethod
    def addIso(mcvirt_instance, path):
        """Copy an ISO to ISOs directory"""
        import shutil

        # Check that file exists
        if (not os.path.isfile(path)):
            raise InvalidISOPathException('Error: \'%s\' is not a file or does not exist' % path)

        # Check that filename ends in '.iso'
        if (not Iso.checkName(path)):
            raise NotAnISOException('Error: \'%s\' is not an ISO' % path)

        filename = Iso.getFilenameFromPath(path)
        Iso.overwriteCheck(mcvirt_instance.ISO_STORAGE_DIR + '/' + filename)

        shutil.copy(path, mcvirt_instance.ISO_STORAGE_DIR)
        full_path = mcvirt_instance.ISO_STORAGE_DIR + '/' + filename
        Iso.setIsoPermissions(full_path)

        return 'ISO added successfully'

    @staticmethod
    def getFilenameFromPath(path):
        """Return filename part of path"""
        filename = path.split('/')[-1]
        if (filename):
            return filename
        else:
            raise NameNotSpecifiedException('Name cannot be determined from "%s".' % path + "\n" +
                                            'Name parameter must be provided')

    @staticmethod
    def checkName(name):
        """Check that name ends in .iso"""
        return name[-4:].lower() == '.iso'

    @staticmethod
    def setIsoPermissions(path):
        """Set permissions to 644"""
        mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(path, mode)

    @staticmethod
    def overwriteCheck(path):
        """Check if a file already exists at path.
           Ask user whether they want to overwrite.
           Returns True if they will overwrite, False otherwise"""

        if (os.path.exists(path)):
            # If there is ask user if they want to overwrite
            overwrite_answer = System.getUserInput(
                '%s already exists, do you want to overwrite it? (Y/n): ' % Iso.getFilename(path))
            if (overwrite_answer.strip() is not 'Y'):
                raise IsoAlreadyExistsException(
                    'Error: An ISO with the same name already exists: "%s"' % path
                )

        return True

    @staticmethod
    def getIsoList(mcvirt_instance):
        """Return a list of ISOs"""

        list = ''
        # Get files in ISO directory
        listing = os.listdir(mcvirt_instance.ISO_STORAGE_DIR)
        for file in listing:
            # If is a file and ends in '.iso' ...
            if (os.path.isfile(mcvirt_instance.ISO_STORAGE_DIR + '/' + file)
                    and Iso.checkName(file)):
                if len(list) > 0:
                    list += '\n'
                list += file

        if (len(list) == 0):
            list = 'No ISO found'

        return list


    @staticmethod
    def deleteIso(mcvirt_instance, name):
        """Delete an ISO"""
        path = mcvirt_instance.ISO_STORAGE_DIR + '/' + name

        # Check exists
        if (not os.path.isfile(path)):
            raise InvalidISOPathException('Error: \'%s\' is not a file or does not exist' % path)
        # Check filename
        if (not Iso.checkName(name)):
            raise NotAnISOException('Error: \'%s\' is not an ISO' % path)

        delete_answer = System.getUserInput('Are you sure you want to delete %s? (Y/n): ' % name)
        if (delete_answer.strip() is 'Y'):
            os.remove(path)
            return '%s successfully deleted' % name
        else:
            return 'ISO not deleted'

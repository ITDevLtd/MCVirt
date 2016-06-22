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

from mcvirt.exceptions import (IsoNotPresentOnDestinationNodeException,
                               InvalidISOPathException, NameNotSpecifiedException,
                               IsoAlreadyExistsException, FailedToRemoveFileException,
                               IsoInUseException)
from mcvirt.system import System
from mcvirt.utils import get_hostname
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.constants import DirectoryLocation


class Iso(PyroObject):
    """Provides management of ISOs for use in MCVirt"""

    def __init__(self, name):
        """Ensures the VM exists, checks the file permissions and creates
           an Iso object"""
        self.name = name

        if not os.path.isfile(self.getPath()):
            raise InvalidISOPathException('Error: \'%s\' does not exist' % self.get_name())

        self.setIsoPermissions()

    def get_name(self):
        """Returns the name of the ISO"""
        return self.name

    def getPath(self):
        """Returns the full path of the ISO"""
        return DirectoryLocation.ISO_STORAGE_DIR + '/' + self.get_name()

    @staticmethod
    def getFilenameFromPath(path, append_iso=True):
        """Return filename part of path"""
        filename = path.split('/')[-1]
        if not filename:
            raise NameNotSpecifiedException('Name cannot be determined from "%s".' % path + "\n" +
                                            'Name parameter must be provided')
        if filename[-4:].lower() != '.iso' and append_iso:
            filename += '.iso'

        return filename

    def setIsoPermissions(self):
        """Set permissions to 644"""
        mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        os.chmod(self.getPath(), mode)

    @staticmethod
    def overwriteCheck(filename, path):
        """Check if a file already exists at path.
           Ask user whether they want to overwrite.
           Returns True if they will overwrite, False otherwise"""

        if os.path.exists(path):
            raise IsoAlreadyExistsException(
                'Error: An ISO with the same name already exists: "%s"' % path
            )

        return True

    def delete(self):
        """Delete an ISO"""
        # Check exists
        in_use = self.inUse()
        if in_use:
            raise IsoInUseException(
                'The ISO is attached to a VM, so cannot be removed: %s' % in_use
            )

        os.remove(self.getPath())

        if not os.path.isfile(self.getPath()):
            return True
        else:
            raise FailedToRemoveFileException(
                'A failure occurred whilst attempting to remove ISO: %s' % self.get_name()
            )

    def inUse(self):
        """Determines if the ISO is currently in use by a VM"""
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for vm_name in virtual_machine_factory.getAllVmNames(node=get_hostname()):
            vm_object = virtual_machine_factory.getVirtualMachineByName(vm_name)
            disk_drive_object = vm_object.get_disk_drive()
            vm_current_iso = disk_drive_object.getCurrentDisk()

            # If the VM has an iso attached, check if the ISO is this one
            if vm_current_iso and vm_current_iso.getPath() == self.getPath():
                return vm_object.get_name()

        return False

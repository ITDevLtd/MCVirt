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

from mcvirt.mcvirt import MCVirtException
from mcvirt.system import System


class IsoNotPresentOnDestinationNodeException(MCVirtException):
    """ISO attached to VM does not exist on destination node
       whilst performing a migration"""
    pass


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
        """Ensures the VM exists, checks the file permissions and creates
           an Iso object"""
        self.name = name
        self.mcvirt_instance = mcvirt_instance

        if (not os.path.isfile(self.getPath())):
            raise InvalidISOPathException('Error: \'%s\' does not exist' % self.getName())

        self.setIsoPermissions()

    def getName(self):
        """Returns the name of the ISO"""
        return self.name

    def getPath(self):
        """Returns the full path of the ISO"""
        return self.mcvirt_instance.ISO_STORAGE_DIR + '/' + self.getName()

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
                '%s already exists, do you want to overwrite it? (Y/n): ' %
                Iso.getFilenameFromPath(path)
            )
            if (overwrite_answer.strip() is not 'Y'):
                raise IsoAlreadyExistsException(
                    'Error: An ISO with the same name already exists: "%s"' % path
                )
            else:
                original_object = Iso(mcvirt_instance, filename)
                if (original_object.inUse()):
                    IsoInUseException('The original ISO is attached to a VM, so cannot be replaced')

        return True

    def delete(self, force=False):
        """Delete an ISO"""
        # Check exists
        in_use = self.inUse()
        if (in_use):
            raise IsoInUseException(
                'The ISO is attached to a VM, so cannot be removed: %s' % in_use
            )

        if not force:
            delete_answer = System.getUserInput(
                'Are you sure you want to delete %s? (Y/n): ' % self.getName()
            )
            if (delete_answer.strip() is not 'Y'):
                return False

        os.remove(self.getPath())

        if not os.path.isfile(self.getPath()):
            return True
        else:
            raise FailedToRemoveFileException(
                'A failure occurred whilst attempting to remove ISO: %s' % self.getName()
            )

    def inUse(self):
        """Determines if the ISO is currently in use by a VM"""
        from virtual_machine.disk_drive import DiskDrive
        from cluster.cluster import Cluster
        from virtual_machine.virtual_machine import VirtualMachine
        for vm_name in VirtualMachine.getAllVms(self.mcvirt_instance,
                                                node=Cluster.getHostname()):
            disk_drive_object = DiskDrive(VirtualMachine(self.mcvirt_instance, vm_name))
            vm_current_iso = disk_drive_object.getCurrentDisk()

            # If the VM has an iso attached, check if the ISO is this one
            if (vm_current_iso and (vm_current_iso.getPath() == self.getPath())):
                return vm_object.getName()

        return False

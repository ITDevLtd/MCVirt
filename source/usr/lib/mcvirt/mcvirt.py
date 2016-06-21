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

import libvirt
import os
from lockfile import FileLock
import socket
import atexit

from exceptions import MCVirtLockException, LibVirtConnectionException
from mcvirt_config import MCVirtConfig
from utils import get_hostname


class MCVirt(object):
    """Provides general MCVirt functions"""

    TEMPLATE_DIR = '/usr/lib/mcvirt/templates'
    BASE_STORAGE_DIR = '/var/lib/mcvirt'
    NODE_STORAGE_DIR = BASE_STORAGE_DIR + '/' + socket.gethostname()
    BASE_VM_STORAGE_DIR = NODE_STORAGE_DIR + '/vm'
    ISO_STORAGE_DIR = NODE_STORAGE_DIR + '/iso'
    LOCK_FILE_DIR = '/var/run/lock/mcvirt'
    LOCK_FILE = LOCK_FILE_DIR + '/lock'

    def __init__(self, uri=None, initialise_nodes=True,
                 ignore_failed_nodes=False, obtain_lock=True):
        """Checks lock file and performs initial connection to libvirt"""
        from auth.auth import Auth
        Auth.checkRootPrivileges()

        # Create an MCVirt config instance and force an upgrade
        MCVirtConfig(perform_upgrade=True, mcvirt_instance=self)

        self.obtained_filelock = False
        self.lockfile_object = None
        self.obtainLock()
        atexit.register(self.cleanup)

    def cleanup(self):
        """Removes MCVirt lock file on object destruction"""
        # Remove lock file
        self.releaseLock()

    def obtainLock(self, timeout=2):
        """Obtains the MCVirt lock file"""
        # Create lock file, if it does not exist
        if (not os.path.isfile(self.LOCK_FILE)):
            if (not os.path.isdir(self.LOCK_FILE_DIR)):
                os.mkdir(self.LOCK_FILE_DIR)
            open(self.LOCK_FILE, 'a').close()

        # Attempt to lock lockfile
        self.lockfile_object = FileLock(self.LOCK_FILE)

        # Check if lockfile object is already locked
        if self.lockfile_object.is_locked():
            raise MCVirtLockException('An instance of MCVirt is already running')
        else:
            self.lockfile_object.acquire(timeout=timeout)

        self.obtained_filelock = True

    def releaseLock(self, initialise_nodes=True):
        """Releases the MCVirt lock file"""
        if self.obtained_filelock:
            self.lockfile_object.release()
            self.lockfile_object = None
            self.obtained_filelock = False


"""Provides a locking mechanism for the MCVirt daemon"""
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
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/>

import atexit
from lockfile import FileLock
import os

from mcvirt.constants import DirectoryLocation
from mcvirt.exceptions import MCVirtLockException


class DaemonLock(object):
    """Provides a lock for the MCVirt daemon"""

    def __init__(self, timeout=2):
        """Create the lock file and lock file object and obtains a lock"""
        # Create lock file, if it does not exist
        if not os.path.isfile(DirectoryLocation.LOCK_FILE):
            if not os.path.isdir(DirectoryLocation.LOCK_FILE_DIR):
                os.mkdir(DirectoryLocation.LOCK_FILE_DIR)
            open(DirectoryLocation.LOCK_FILE, 'a').close()

        # Attempt to lock lockfile
        self.lockfile_object = FileLock(DirectoryLocation.LOCK_FILE)

        # Check if lockfile object is already locked
        if self.lockfile_object.is_locked():
            raise MCVirtLockException('An instance of MCVirt is already running')
        else:
            self.lockfile_object.acquire(timeout=timeout)
        atexit.register(self.lockfile_object.release)

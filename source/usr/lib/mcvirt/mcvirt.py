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
        self.libvirt_uri = 'qemu://%s/system' % get_hostname()
        self.connection = None
        # Create an MCVirt config instance and force an upgrade
        MCVirtConfig(perform_upgrade=True, mcvirt_instance=self)

        # Cluster configuration
        self.initialise_nodes = initialise_nodes
        self.ignore_failed_nodes = ignore_failed_nodes
        self.remote_nodes = {}
        self.libvirt_node_connections = {}
        self.failed_nodes = []
        self.ignore_drbd = False

        self.obtained_filelock = False
        self.lockfile_object = None
        self.obtainLock()
        atexit.register(self.cleanup)
        self.getLibvirtConnection()

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

    def getRemoteLibvirtConnection(self, remote_node):
        """Obtains and caches connections to remote libvirt daemons"""
        # Check if a connection has already been established
        if remote_node.name not in self.libvirt_node_connections:
            # If not, establish a connection
            libvirt_url = 'qemu://%s/system' % remote_node.name
            connection = libvirt.open(libvirt_url)

            if connection is None:
                raise ConnectionFailureToRemoteLibvirtInstance(
                    'Failed to connect to remote libvirt daemon on %s' %
                    remote_node.name
                )
            self.libvirt_node_connections[remote_node.name] = connection

        return self.libvirt_node_connections[remote_node.name]

    def getLibvirtConnection(self):
        """
        Obtains a libvirt connection. If one does not exist,
        connect to libvirt and store the connection as an object variable.
        Exit if an error occurs whilst connecting.
        """
        self.connection = libvirt.open(self.libvirt_uri)
        if self.connection is None:
            raise LibVirtConnectionException(
                'Failed to open connection to the hypervisor'
            )
        return self.connection

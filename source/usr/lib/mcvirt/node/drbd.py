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

from Cheetah.Template import Template
import os
import socket
import thread
from texttable import Texttable
import Pyro4

from mcvirt.exceptions import DrbdNotInstalledException, DrbdAlreadyEnabled, DrbdNotEnabledOnNode
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import lockingMethod
from mcvirt.utils import get_hostname
from mcvirt.constants import DirectoryLocation


class Drbd(PyroObject):
    """Performs configuration of Drbd on the node"""

    CONFIG_DIRECTORY = '/etc/drbd.d'
    GLOBAL_CONFIG = CONFIG_DIRECTORY + '/global_common.conf'
    GLOBAL_CONFIG_TEMPLATE = DirectoryLocation.TEMPLATE_DIR + '/drbd_global.conf'
    DrbdADM = '/sbin/drbdadm'
    CLUSTER_SIZE = 2

    @Pyro4.expose()
    def isEnabled(self):
        """Determines whether Drbd is enabled on the node or not"""
        return self.get_config()['enabled']

    @Pyro4.expose()
    def isInstalled(self):
        """Determines if the 'drbdadm' command is present to determine if the
           'drbd8-utils' package is installed"""
        return os.path.isfile(self.DrbdADM)

    def ensureInstalled(self):
        """Ensures that Drbd is installed on the node"""
        if not self.isInstalled():
            raise DrbdNotInstalledException('drbdadm not found' +
                                            ' (Is the drbd8-utils package installed?)')

    @Pyro4.expose()
    @lockingMethod()
    def enable(self, secret=None):
        """Ensures the machine is suitable to run Drbd"""
        # Ensure user has the ability to manage Drbd
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_Drbd)

        # Ensure that Drbd is installed
        self.ensureInstalled()

        if self.isEnabled() and self._is_cluster_master:
            raise DrbdAlreadyEnabled('Drbd has already been enabled on this node')

        if secret is None:
            secret = self.generateSecret()

        # Set the secret in the local configuration
        self.setSecret(secret)

        if self._is_cluster_master:
            # Enable Drbd on the remote nodes
            cluster = self._get_registered_object('cluster')

            def remoteCommand(node):
                remote_drbd = node.get_connection('node_drbd')
                remote_drbd.enable(secret=secret)

            cluster.run_remote_command(callback_method=remoteCommand)

        # Generate the global Drbd configuration
        self.generateConfig()

        # Update the local configuration
        def update_config(config):
            config['drbd']['enabled'] = 1
        MCVirtConfig().update_config(update_config, 'Enabled Drbd')

    def get_config(self):
        """Returns the global Drbd configuration"""
        mcvirt_config = MCVirtConfig()
        if 'drbd' in mcvirt_config.get_config().keys():
            return mcvirt_config.get_config()['drbd']
        else:
            return self.get_default_config()

    @staticmethod
    def get_default_config():
        default_config = \
            {
                'enabled': 0,
                'secret': '',
                'sync_rate': '10M',
                'protocol': 'C'
            }
        return default_config

    def generateConfig(self):
        """Generates the Drbd configuration"""
        # Obtain the MCVirt Drbd config
        drbd_config = self.get_config()

        # Replace the variables in the template with the local Drbd configuration
        config_content = Template(file=self.GLOBAL_CONFIG_TEMPLATE, searchList=[drbd_config])

        # Write the Drbd configuration
        fh = open(self.GLOBAL_CONFIG, 'w')
        fh.write(config_content.respond())
        fh.close()

        # Update Drbd running configuration
        self.adjustDrbdConfig()

    def generateSecret(self):
        """Generates a random secret for Drbd"""
        import random
        import string

        return ''.join([random.choice(string.ascii_letters + string.digits) for _ in xrange(16)])

    def setSecret(self, secret):
        """Sets the Drbd configuration in the global MCVirt config file"""
        def update_config(config):
            config['drbd']['secret'] = secret
        MCVirtConfig().update_config(update_config, 'Set Drbd secret')

    def adjustDrbdConfig(self, resource='all'):
        """Performs a Drbd adjust, which updates the Drbd running configuration"""
        if (len(self.getAllDrbdHardDriveObjects())):
            System.runCommand([Drbd.DrbdADM, 'adjust', resource])

    def getAllDrbdHardDriveObjects(self, include_remote=False):
        hard_drive_objects = []
        vm_factory = self._get_registered_object('virtual_machine_factory')
        for vm_object in vm_factory.getAllVirtualMachines():
            if (get_hostname() in vm_object.getAvailableNodes() or include_remote):
                all_hard_drive_objects = vm_object.getHardDriveObjects()

                for hard_drive_object in all_hard_drive_objects:
                    if (hard_drive_object.getType() is 'Drbd'):
                        hard_drive_objects.append(hard_drive_object)

        return hard_drive_objects

    def getUsedDrbdPorts(self):
        """Returns a list of used Drbd ports"""
        return [hdd.drbd_port for hdd in self.getAllDrbdHardDriveObjects(include_remote=True)]

    def getUsedDrbdMinors(self):
        """Returns a list of used Drbd minor IDs"""
        return [hdd.drbd_minor for hdd in self.getAllDrbdHardDriveObjects(include_remote=True)]

    @Pyro4.expose()
    def list(self):
        """Lists the Drbd volumes and statuses"""
        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Volume Name', 'VM', 'Minor', 'Port', 'Role', 'Connection State',
                      'Disk State', 'Sync Status'))

        # Set column alignment and widths
        table.set_cols_width((30, 20, 5, 5, 20, 20, 20, 13))
        table.set_cols_align(('l', 'l', 'c', 'c', 'l', 'c', 'l', 'c'))

        # Iterate over Drbd objects, adding to the table
        for drbd_object in self.getAllDrbdHardDriveObjects(True):
            table.add_row((drbd_object.resource_name,
                           drbd_object.vm_object.get_name(),
                           drbd_object.drbd_minor,
                           drbd_object.drbd_port,
                           'Local: %s, Remote: %s' % (drbd_object._drbdGetRole()[0].name,
                                                      drbd_object._drbdGetRole()[1].name),
                           drbd_object._drbdGetConnectionState().name,
                           'Local: %s, Remote: %s' % (drbd_object._drbdGetDiskState()[0].name,
                                                      drbd_object._drbdGetDiskState()[1].name),
                           'In Sync' if drbd_object._isInSync() else 'Out of Sync'))
        return table.draw()

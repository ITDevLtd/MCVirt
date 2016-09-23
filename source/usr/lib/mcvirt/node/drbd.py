"""Provides interface to mange the DRBD installation."""

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
from texttable import Texttable
import Pyro4
import string
import json
from binascii import hexlify

from mcvirt.exceptions import DrbdNotInstalledException, DrbdAlreadyEnabled
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import get_hostname
from mcvirt.constants import DirectoryLocation


class Drbd(PyroObject):
    """Performs configuration of DRBD on the node"""

    CONFIG_DIRECTORY = '/etc/drbd.d'
    GLOBAL_CONFIG = CONFIG_DIRECTORY + '/global_common.conf'
    GLOBAL_CONFIG_TEMPLATE = DirectoryLocation.TEMPLATE_DIR + '/drbd_global.conf'
    DrbdADM = '/sbin/drbdadm'
    CLUSTER_SIZE = 2

    def initialise(self):
        """Ensure that DRBD user exists and that hook configuration
        exists
        """
        if self.is_enabled():
            self.check_hook_configuration()
            if MCVirtConfig.REGENERATE_DRBD_CONFIG:
                MCVirtConfig.REGENERATE_DRBD_CONFIG = False
                self.generate_config()

    def check_hook_configuration(self):
        """Ensure that DRBD user exists and that hook configuration
        exists
        """
        user_factory = self._get_registered_object('user_factory')
        if (not os.path.exists(DirectoryLocation.DRBD_HOOK_CONFIG) or
                not len(user_factory.get_all_user_objects(user_classes=['DrbdHookUser']))):

            # Generate hook user
            hook_user, hook_pass = user_factory.generate_user(user_type='DrbdHookUser')

            # Write DRBD hook script configuration file
            with open(DirectoryLocation.DRBD_HOOK_CONFIG, 'w') as fh:
                json.dump({'username': hook_user, 'password': hook_pass}, fh)

    @Expose()
    def is_enabled(self):
        """Determine whether Drbd is enabled on the node or not"""
        return self.get_config()['enabled']

    @Expose()
    def is_installed(self):
        """Determine if the 'drbdadm' command is present to determine if the
        'drbd8-utils' package is installed
        """
        return os.path.isfile(self.DrbdADM)

    def ensure_installed(self):
        """Ensure that Drbd is installed on the node"""
        if not self.is_installed():
            raise DrbdNotInstalledException('drbdadm not found' +
                                            ' (Is the drbd8-utils package installed?)')

    @Expose(locking=True)
    def enable(self, secret=None):
        """Ensure the machine is suitable to run Drbd"""
        # Ensure user has the ability to manage Drbd
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_DRBD)

        # Ensure that Drbd is installed
        self.ensure_installed()

        if self.is_enabled() and self._is_cluster_master:
            raise DrbdAlreadyEnabled('Drbd has already been enabled on this node')

        if secret is None:
            secret = self.generate_secret()

        self.check_hook_configuration()

        # Set the secret in the local configuration
        self.set_secret(secret)

        if self._is_cluster_master:
            # Enable Drbd on the remote nodes
            cluster = self._get_registered_object('cluster')

            def remote_command(node):
                remote_drbd = node.get_connection('node_drbd')
                remote_drbd.enable(secret=secret)

            cluster.run_remote_command(callback_method=remote_command)

        # Generate the global Drbd configuration
        self.generate_config()

        # Update the local configuration
        def update_config(config):
            config['drbd']['enabled'] = 1
        MCVirtConfig().update_config(update_config, 'Enabled Drbd')

    def get_config(self):
        """Return the global Drbd configuration"""
        mcvirt_config = MCVirtConfig()
        if 'drbd' in mcvirt_config.get_config().keys():
            return mcvirt_config.get_config()['drbd']
        else:
            return self.get_default_config()

    @staticmethod
    def get_default_config():
        """Return the default configuration for DRBD"""
        default_config = \
            {
                'enabled': 0,
                'secret': '',
                'sync_rate': '10M',
                'protocol': 'C'
            }
        return default_config

    def generate_config(self):
        """Generate the Drbd configuration"""
        # Obtain the MCVirt Drbd config
        drbd_config = self.get_config()

        # Replace the variables in the template with the local Drbd configuration
        config_content = Template(file=self.GLOBAL_CONFIG_TEMPLATE, searchList=[drbd_config])

        # Write the Drbd configuration
        fh = open(self.GLOBAL_CONFIG, 'w')
        fh.write(config_content.respond())
        fh.close()

        # Update Drbd running configuration
        self.adjust_drbd_config()

    def generate_secret(self):
        """Generate a random secret for Drbd"""
        return hexlify(os.urandom(16))

    def set_secret(self, secret):
        """Set the Drbd configuration in the global MCVirt config file"""
        def update_config(config):
            config['drbd']['secret'] = secret
        MCVirtConfig().update_config(update_config, 'Set Drbd secret')

    def adjust_drbd_config(self, resource='all'):
        """Perform a Drbd adjust, which updates the Drbd running configuration"""
        if (len(self.get_all_drbd_hard_drive_object())):
            System.runCommand([Drbd.DrbdADM, 'adjust', resource])

    def get_all_drbd_hard_drive_object(self, include_remote=False):
        """Obtain all hard drive objects that are backed by DRBD"""
        hard_drive_objects = []
        vm_factory = self._get_registered_object('virtual_machine_factory')
        for vm_object in vm_factory.getAllVirtualMachines():
            if (get_hostname() in vm_object.getAvailableNodes() or include_remote):
                all_hard_drive_objects = vm_object.getHardDriveObjects()

                for hard_drive_object in all_hard_drive_objects:
                    if (hard_drive_object.get_type() is 'Drbd'):
                        hard_drive_objects.append(hard_drive_object)

        return hard_drive_objects

    def get_used_drbd_ports(self):
        """Return a list of used Drbd ports"""
        return [hdd.drbd_port for hdd in self.get_all_drbd_hard_drive_object(include_remote=True)]

    def get_used_drbd_minors(self):
        """Return a list of used Drbd minor IDs"""
        return [hdd.drbd_minor for hdd in self.get_all_drbd_hard_drive_object(include_remote=True)]

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses"""
        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Volume Name', 'VM', 'Minor', 'Port', 'Role', 'Connection State',
                      'Disk State', 'Sync Status'))

        # Set column alignment and widths
        table.set_cols_width((30, 20, 5, 5, 20, 20, 20, 13))
        table.set_cols_align(('l', 'l', 'c', 'c', 'l', 'c', 'l', 'c'))

        # Iterate over Drbd objects, adding to the table
        for drbd_object in self.get_all_drbd_hard_drive_object(True):
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

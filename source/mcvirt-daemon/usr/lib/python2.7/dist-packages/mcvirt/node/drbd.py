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
import json
from binascii import hexlify

from mcvirt.exceptions import DrbdNotInstalledException, DrbdAlreadyEnabled
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import get_hostname
from mcvirt.constants import DirectoryLocation


class Drbd(PyroObject):
    """Performs configuration of DRBD on the node."""

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
        user_factory = self.po__get_registered_object('user_factory')
        if (not os.path.exists(DirectoryLocation.DRBD_HOOK_CONFIG) or
                not len(user_factory.get_all_user_objects(user_classes=['DrbdHookUser']))):

            # Generate hook user
            hook_user, hook_pass = user_factory.generate_user(user_type='DrbdHookUser')

            # Write DRBD hook script configuration file
            with open(DirectoryLocation.DRBD_HOOK_CONFIG, 'w') as fh:
                json.dump({'username': hook_user, 'password': hook_pass}, fh)

    @Expose()
    def is_enabled(self, node=None):
        """Determine whether Drbd is enabled on the node or not."""
        cluster = self.po__get_registered_object('cluster')
        if node is None or node == get_hostname():
            return self.get_config()['enabled']

        def get_remote_enabled(connection):
            """Obtain remote DRBD enabled."""
            remote_node_drbd = connection.get_connection('node_drbd')
            return remote_node_drbd.is_enabled()
        return cluster.run_remote_command(get_remote_enabled, node=node)

    @Expose()
    def is_installed(self):
        """Determine if the 'drbdadm' command is present to determine if the
        'drbd8-utils' package is installed
        """
        return os.path.isfile(self.DrbdADM)

    def ensure_installed(self):
        """Ensure that Drbd is installed on the node."""
        if not self.is_installed():
            raise DrbdNotInstalledException('drbdadm not found' +
                                            ' (Is the drbd8-utils package installed?)')

    @Expose(locking=True)
    def enable(self, secret=None):
        """Ensure the machine is suitable to run Drbd."""
        # Ensure user has the ability to manage Drbd
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_DRBD)

        # Ensure that Drbd is installed
        self.ensure_installed()

        if self.is_enabled() and self.po__is_cluster_master:
            raise DrbdAlreadyEnabled('Drbd has already been enabled on this node')

        if secret is None:
            secret = self.generate_secret()

        self.check_hook_configuration()

        # Set the secret in the local configuration
        self.set_secret(secret)

        if self.po__is_cluster_master:
            # Enable Drbd on the remote nodes
            cluster = self.po__get_registered_object('cluster')

            def remote_command(node):
                """Enable DRBD on remote node, specifying the secret."""
                remote_drbd = node.get_connection('node_drbd')
                remote_drbd.enable(secret=secret)

            cluster.run_remote_command(callback_method=remote_command)

        # Generate the global Drbd configuration
        self.generate_config()

        # Update the local configuration
        def update_config(config):
            """Enable DRBD in local MCVirt config."""
            config['drbd']['enabled'] = True
        MCVirtConfig().update_config(update_config, 'Enabled Drbd')

    def get_config(self):
        """Return the global Drbd configuration."""
        mcvirt_config = MCVirtConfig()
        return mcvirt_config.get_config()['drbd']

    def generate_config(self):
        """Generate the Drbd configuration."""
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
        """Generate a random secret for Drbd."""
        return hexlify(os.urandom(16))

    def set_secret(self, secret):
        """Set the Drbd configuration in the global MCVirt config file."""
        def update_config(config):
            """Set secret in MCVirt config."""
            config['drbd']['secret'] = secret
        MCVirtConfig().update_config(update_config, 'Set Drbd secret')

    def adjust_drbd_config(self, resource='all'):
        """Perform a Drbd adjust, which updates the Drbd running configuration."""
        if len(self.get_all_drbd_hard_drive_object()):
            System.runCommand([Drbd.DrbdADM, 'adjust', resource])

    def get_all_drbd_hard_drive_object(self, include_remote=False):
        """Obtain all hard drive objects that are backed by DRBD."""
        hard_drive_objects = []
        hdd_factory = self.po__get_registered_object('hard_drive_factory')
        for hdd_object in hdd_factory.get_all():
            if ((get_hostname() in hdd_object.nodes or include_remote) and
                    hdd_object.get_type() == 'Drbd'):
                hard_drive_objects.append(hdd_object)

        return hard_drive_objects

    def get_used_drbd_ports(self):
        """Return a list of used Drbd ports."""
        return [hdd.get_drbd_port(generate=False)
                for hdd in self.get_all_drbd_hard_drive_object(include_remote=True)]

    def get_used_drbd_minors(self):
        """Return a list of used Drbd minor IDs."""
        return [hdd.get_drbd_minor(generate=False)
                for hdd in self.get_all_drbd_hard_drive_object(include_remote=True)]

    @Expose()
    def list(self):
        """List the Drbd volumes and statuses."""
        # Create table and add headers
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Volume Name', 'Minor', 'Port', 'Role', 'Connection State',
                      'Disk State', 'Sync Status'))

        # Set column alignment and widths
        table.set_cols_width((30, 5, 5, 20, 20, 20, 13))
        table.set_cols_align(('l', 'c', 'c', 'l', 'c', 'l', 'c'))

        # Manually set permissions asserted, as this function can
        # run high privilege calls, but doesn't not require
        # permission checking
        with self.po__get_registered_object('auth').elevate_permissions(PERMISSIONS.MANAGE_DRBD):
            # Iterate over Drbd objects, adding to the table
            for drbd_object in self.get_all_drbd_hard_drive_object(True):
                remote_node = None
                if not (drbd_object.get_virtual_machine() and
                        drbd_object.get_virtual_machine().is_registered_locally()):
                    node_name = (drbd_object.get_virtual_machine().get_node()
                                 if drbd_object.get_virtual_machine() else
                                 None)
                    available_nodes = drbd_object.nodes
                    if node_name is None:
                        node_name, sec_remote_node_name = available_nodes
                    else:
                        available_nodes.remove(node_name)
                        sec_remote_node_name = available_nodes[0]
                    # drbd_object, remote_node = drbd_object.get_remote_object(
                    #     node_name=drbd_object.get_vm_object().getNode(), return_node=True
                    # )
                else:
                    node_name = 'Local'
                    sec_remote_node_name = 'Remote'
                table.add_row((drbd_object.get_resource_name(),
                               drbd_object.drbd_minor,
                               drbd_object.drbd_port,
                               '%s: %s, %s: %s' % (node_name, drbd_object.drbdGetRole()[0][0],
                                                   sec_remote_node_name,
                                                   drbd_object.drbdGetRole()[1][0]),
                               drbd_object.drbdGetConnectionState()[0],
                               '%s: %s, %s: %s' % (node_name, drbd_object.drbdGetDiskState()[0][0],
                                                   sec_remote_node_name,
                                                   drbd_object.drbdGetDiskState()[1][0]),
                               'In Sync' if drbd_object.isInSync() else 'Out of Sync'))
        return table.draw()

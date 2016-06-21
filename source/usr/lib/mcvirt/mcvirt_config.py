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

import os

from config_file import ConfigFile


class MCVirtConfig(ConfigFile):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    def __init__(self, mcvirt_instance=None, perform_upgrade=False):
        """Sets member variables and obtains libvirt domain object"""
        from mcvirt import MCVirt

        self.config_file = MCVirt.NODE_STORAGE_DIR + '/config.json'

        if not os.path.isdir(MCVirt.BASE_STORAGE_DIR):
            self._createConfigDirectories()

        if not os.path.isfile(self.config_file):
            self.create()

        # If performing an upgrade has been specified, do so
        if perform_upgrade and mcvirt_instance:
            self.upgrade(mcvirt_instance)

    def _createConfigDirectories(self):
        """Creates the configuration directories for the node"""
        # Initialise the git repository
        from mcvirt import MCVirt
        import stat

        os.mkdir(MCVirt.BASE_STORAGE_DIR)
        os.mkdir(MCVirt.NODE_STORAGE_DIR)
        os.mkdir(MCVirt.BASE_VM_STORAGE_DIR)
        os.mkdir(MCVirt.ISO_STORAGE_DIR)

        # Set permission on MCVirt directory
        self.setConfigPermissions()

    def getListenAddress(self):
        """Returns the address that should be used for listening
           for connections - the stored IP address, if configured, else
           all interfaces"""
        config_ip = self.getConfig()['cluster']['cluster_ip']
        return config_ip if config_ip else '0.0.0.0'

    def create(self):
        """Creates a basic VM configuration for new VMs"""
        from node.drbd import DRBD as NodeDRBD

        # Create basic config
        json_data = \
            {
                'version': self.CURRENT_VERSION,
                'superusers': [],
                'permissions':
                {
                    'user': [],
                    'owner': [],
                },
                'vm_storage_vg': '',
                'cluster':
                {
                    'cluster_ip': '',
                    'nodes': {}
                },
                'virtual_machines': [],
                'networks': {
                    'default': 'virbr0'
                },
                'drbd': NodeDRBD.getDefaultConfig(),
                'git':
                {
                    'repo_domain': '',
                    'repo_path': '',
                    'repo_protocol': '',
                    'username': '',
                    'password': '',
                    'commit_name': '',
                    'commit_email': ''
                },
                'users': {},
                'libvirt_configured': False
            }

        # Write the configuration to disk
        MCVirtConfig._writeJSON(json_data, self.config_file)

    def _upgrade(self, mcvirt_instance, config):
        """Perform an upgrade of the configuration file"""
        pass
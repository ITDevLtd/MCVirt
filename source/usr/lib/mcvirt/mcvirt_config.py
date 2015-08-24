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

        if (not os.path.isdir(MCVirt.BASE_STORAGE_DIR)):
            self._createConfigDirectories()

        if (not os.path.isfile(self.config_file)):
            self.create()

        # If performing an upgrade has been specified, do so
        if (perform_upgrade and mcvirt_instance):
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
        os.chmod(MCVirt.BASE_STORAGE_DIR, stat.S_IRWXU | stat.S_IRGRP 
                                          | stat.S_IXGRP | stat.S_IROTH 
                                          | stat.S_IXOTH)
        os.chown(MCVirt.BASE_STORAGE_DIR, 0, 0)

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
                'networks': {},
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
                }
            }

        # Write the configuration to disk
        MCVirtConfig._writeJSON(json_data, self.config_file)

    def _upgrade(self, mcvirt_instance, config):
        """Perform an upgrade of the configuration file"""
        if (self._getVersion() < 1):
            # Add new global permission groups
            for new_permission_goup in ['user', 'owner']:
                if (new_permission_goup not in config['permissions'].keys()):
                    config['permissions'][new_permission_goup] = []

            # Add cluster configuration to config
            config['cluster'] = {
                'cluster_ip': '',
                'nodes': {}
            }

            # Obtain list of virtual machines from LibVirt
            all_domains = mcvirt_instance.getLibvirtConnection().listAllDomains()

            # Add virtual machines to global configuration
            config['virtual_machines'] = [vm.name() for vm in all_domains]

            # Obtain list of networks from LibVirt
            all_networks = mcvirt_instance.getLibvirtConnection().listAllNetworks()
            config['networks'] = {}
            for network in all_networks:
                config['networks'][network.name()] = network.bridgeName()

            # Add default DRBD configuration
            config['drbd'] = {
                'enabled': 0,
                'secret': '',
                'sync_rate': '10M',
                'protocol': 'C'
            }

            # Create git configuration
            config['git'] = {
                'repo_domain': '',
                'repo_path': '',
                'repo_protocol': '',
                'username': '',
                'password': '',
                'commit_name': '',
                'commit_email': ''
            }

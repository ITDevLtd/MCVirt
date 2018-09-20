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

from mcvirt.config_file import ConfigFile
from mcvirt.constants import DirectoryLocation
from mcvirt.utils import get_hostname


class MCVirtConfig(ConfigFile):
    """Provides operations to obtain and set the MCVirt
    configuration for a VM
    """

    REGENERATE_DRBD_CONFIG = False

    def __init__(self):
        """Set member variables and obtains libvirt domain object"""
        self.config_file = DirectoryLocation.NODE_STORAGE_DIR + '/config.json'

        if not os.path.isdir(DirectoryLocation.BASE_STORAGE_DIR):
            self._createConfigDirectories()

        if not os.path.isfile(self.config_file):
            self.create()

        # If performing an upgrade has been specified, do so
        self.upgrade()

    def _createConfigDirectories(self):
        """Create the configuration directories for the node"""
        # Initialise the git repository
        os.mkdir(DirectoryLocation.BASE_STORAGE_DIR)
        os.mkdir(DirectoryLocation.NODE_STORAGE_DIR)
        os.mkdir(DirectoryLocation.BASE_VM_STORAGE_DIR)
        os.mkdir(DirectoryLocation.ISO_STORAGE_DIR)

        # Set permission on MCVirt directory
        self.setConfigPermissions()

    def getListenAddress(self):
        """Return the address that should be used for listening
        for connections - the stored IP address, if configured, else
        all interfaces
        """
        config_ip = self.get_config()['cluster']['cluster_ip']
        return config_ip if config_ip else '0.0.0.0'

    def create(self):
        """Create a basic VM configuration for new VMs"""
        from node.drbd import Drbd as NodeDrbd

        # Create basic config
        json_data = \
            {
                'version': self.CURRENT_VERSION,
                'superusers': ["mjc"],
                'permissions':
                {
                    'user': [],
                    'owner': [],
                },
                'cluster':
                {
                    'cluster_ip': '',
                    'nodes': {}
                },
                'virtual_machines': [],
                'networks': {
                },
                'drbd': NodeDrbd.get_default_config(),
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
                'users': {
                    "mjc": {
                        "password": ("$p5k2$3e8$e30d99dc817ad452ec124e4ac011637652c54eeb0abe5dff09"
                                     "ac8b85d7331707$ChiC2SGEokh""HietmLcCQNjtMLf30Oggr"),
                        "salt": "e30d99dc817ad452ec124e4ac011637652c54eeb0abe5dff09ac8b85d7331707",
                        "user_type": "LocalUser"
                    }
                },
                'libvirt_configured': False,
                'log_level': 'WARNING',
                'ldap': {
                    'enabled': False,
                    'server_uri': None,
                    'base_dn': None,
                    'user_search': None,
                    'bind_dn': None,
                    'bind_pass': None,
                    'username_attribute': None
                },
                'session_timeout': 30,
                'autostart_interval': 300,
                'storage_backends': {}
            }

        # Write the configuration to disk
        MCVirtConfig._writeJSON(json_data, self.config_file)

    def _upgrade(self, config):
        """Perform an upgrade of the configuration file"""
        if config['version'] < 5:
            # Rename user_type for local users to new 'LocalUser' type
            for username in config['users']:
                if config['users'][username]['user_type'] == 'User':
                    config['users'][username]['user_type'] = 'LocalUser'
            config['ldap'] = {'server_uri': None, 'base_dn': None, 'user_search': None,
                              'bind_dn': None, 'bind_pass': None,
                              'username_attribute': None, 'enabled': False}

        if config['version'] < 6:
            MCVirtConfig.REGENERATE_DRBD_CONFIG = True

        if config['version'] < 7:
            config['session_timeout'] = 30

        if config['version'] < 8:
            config['autostart_interval'] = 300

        if config['version'] < 11:
            config['storage_backends'] = {}
            if config['vm_storage_vg']:
                config['storage_backends']['default'] = {
                    'type': 'Lvm',
                    'volume_group_name': config['vm_storage_vg']
                }
                del config['vm_storage_vg']
            config['cluster']['node_name'] = get_hostname()
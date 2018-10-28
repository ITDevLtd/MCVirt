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

from mcvirt.config.base import Base
from mcvirt.exceptions import IntermediateUpgradeRequiredError
from mcvirt.constants import (DirectoryLocation,
                              DEFAULT_STORAGE_NAME, DEFAULT_STORAGE_ID,
                              DEFAULT_USER_GROUP_ID, DEFAULT_OWNER_GROUP_ID)
from mcvirt.utils import get_hostname
import mcvirt.config.migrations.core as migrations


class Core(Base):
    """Provides operations to obtain and set the MCVirt
    configuration for a VM
    """

    REGENERATE_DRBD_CONFIG = False

    def __init__(self):
        """Set member variables and obtains libvirt domain object"""
        if not os.path.isdir(DirectoryLocation.BASE_STORAGE_DIR):
            self._createConfigDirectories()

        if not os.path.isfile(self.config_file):
            self.create()

        # If performing an upgrade has been specified, do so
        self.upgrade()

    @property
    def config_file(self):
        """Return the location of the config file"""
        return DirectoryLocation.NODE_STORAGE_DIR + '/config.json'

    def _get_config_subtree_array(self):
        """Get a list of dict keys to traverse the parent config"""
        # Return empty array as MCVirt uses base config
        return []

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
        # Create basic config
        json_data = \
            {
                'version': self.CURRENT_VERSION,
                'superusers': ['mjc'],
                'groups':
                {
                    DEFAULT_USER_GROUP_ID: {
                        'name': 'user',
                        'permissions': [
                            'CHANGE_VM_POWER_STATE',
                            'VIEW_VNC_CONSOLE',
                            'TEST_USER_PERMISSION'
                        ],
                        'users': []
                    },
                    DEFAULT_OWNER_GROUP_ID: {
                        'name': 'owner',
                        'permissions': [
                            'CHANGE_VM_POWER_STATE',
                            'MANAGE_VM_USERS',
                            'VIEW_VNC_CONSOLE',
                            'CLONE_VM',
                            'DELETE_CLONE',
                            'DUPLICATE_VM',
                            'TEST_OWNER_PERMISSION',
                            'MANAGE_GROUP_MEMBERS'
                        ],
                        'users': []
                    }
                },
                'cluster':
                {
                    'cluster_ip': '',
                    'node_name': get_hostname(),
                    'nodes': {}
                },
                'virtual_machines': {},
                'networks': {
                },
                'drbd': {
                    'enabled': False,
                    'secret': None,
                    'sync_rate': '10M',
                    'protocol': 'C'
                },
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
                'storage_backends': {},
                'default_storage_configured': True,
                'agent': {
                    # Allow 10 second connection timeout
                    'connection_timeout': 10
                },
                'watchdog': {
                    # Default to 60 second watchdog interval
                    'interval': 60,
                    # By default, reset VM after 3 failed checks
                    'reset_fail_count': 3,
                    # By default, wait 5 minutes for VM to boot
                    'boot_wait': 300
                }
            }

        # Write the configuration to disk
        Core._writeJSON(json_data, self.config_file)

    def _upgrade(self, config):
        """Perform an upgrade of the configuration file"""
        if self._getVersion() < 16:
            raise IntermediateUpgradeRequiredError(
                'Must upgrade to MCVirt v10.0.2 before upgrading to <=v11.0.0')

        if self._getVersion() < 17:
            migrations.v17.migrate(self, config)

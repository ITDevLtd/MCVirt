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
import hashlib

from mcvirt.config_file import ConfigFile
from mcvirt.constants import (DirectoryLocation,
                              DEFAULT_STORAGE_NAME, DEFAULT_STORAGE_ID,
                              DEFAULT_USER_GROUP_ID, DEFAULT_OWNER_GROUP_ID)
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
                            'TEST_OWNER_PERMISSION'
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
                'storage_backends': {},
                'default_storage_configured': True
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
            # If the vm_storage_vg was configured, create a base
            # configuration for the deafult storage backend
            if config['vm_storage_vg']:
                config['storage_backends'][DEFAULT_STORAGE_ID] = {
                    'name': DEFAULT_STORAGE_NAME,
                    'type': 'Lvm',
                    'location': None,
                    'nodes': {
                        get_hostname(): {
                            'location': config['vm_storage_vg']
                        }
                    }
                }
                del config['vm_storage_vg']
            # Mark the default storage as not being configured.
            config['default_storage_configured'] = False

            # Define the hostname of the local machine in the config file
            config['cluster']['node_name'] = get_hostname()

        # Only update storage backend config, if they already exist,
        # otherwise, the v9 upgrade will take care of it
        elif config['version'] < 12:
            new_storage_config = {}
            for storage_name in config['storage_backends'].keys():
                # Obtain config for storage backend and append name to config
                storage_config = config['storage_backends'][storage_name]
                storage_config['name'] = storage_name

                # Generate ID for storage backend
                name_checksum = hashlib.sha512(storage_name).hexdigest()
                date_checksum = hashlib.sha512('0').hexdigest()
                storage_id = 'sb-%s-%s' % (name_checksum[0:16], date_checksum[0:24])

                # Add config back to main config, keyed with ID and remove original
                # config
                new_storage_config[storage_id] = storage_config
            config['storage_backends'] = new_storage_config

        if config['version'] < 13:
            # Replace the permissions config with group objects
            group_config = {
                DEFAULT_USER_GROUP_ID: {
                    'name': 'user',
                    'permissions': [
                        'CHANGE_VM_POWER_STATE',
                        'VIEW_VNC_CONSOLE',
                        'TEST_USER_PERMISSION'
                    ],
                    'users': list(config['permissions']['user'])
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
                        'TEST_OWNER_PERMISSION'
                    ],
                    'users': list(config['permissions']['owner'])
                }
            }
            config['groups'] = group_config
            del config['permissions']

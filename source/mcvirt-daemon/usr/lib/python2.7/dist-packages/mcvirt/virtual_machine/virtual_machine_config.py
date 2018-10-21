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

from mcvirt.exceptions import ConfigFileCouldNotBeFoundException
from mcvirt.config_file import ConfigFile
from mcvirt.constants import (AutoStartStates,
                              DEFAULT_USER_GROUP_ID,
                              DEFAULT_OWNER_GROUP_ID)
from mcvirt.utils import get_hostname


class VirtualMachineConfig(ConfigFile):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    def __init__(self, vm_object):
        """Sets member variables and obtains libvirt domain object"""
        self.git_object = None
        self.vm_object = vm_object
        self.config_file = VirtualMachineConfig.get_config_path(self.vm_object.name)
        if not os.path.isfile(self.config_file):
            raise ConfigFileCouldNotBeFoundException(
                'Could not find config file for %s' % vm_object.name
            )

        # Perform upgrade of configuration
        self.upgrade()

    @staticmethod
    def get_config_path(vm_name):
        """Provides the path of the VM-spefic configuration file"""
        from mcvirt.virtual_machine.virtual_machine import VirtualMachine
        return '%s/config.json' % VirtualMachine.get_vm_dir(vm_name)

    @staticmethod
    def create(vm_name, available_nodes, cpu_cores, memory_allocation, graphics_driver):
        """Creates a basic VM configuration for new VMs"""
        # @TODO Move import to main
        from mcvirt.virtual_machine.virtual_machine import LockStates

        # Create basic config
        json_data = \
            {
                'version': VirtualMachineConfig.CURRENT_VERSION,
                'applied_version': VirtualMachineConfig.CURRENT_VERSION,
                'permissions':
                {
                    'users': {},
                    'groups': {},
                },
                'hard_disks': {},
                'storage_type': None,
                'memory_allocation': memory_allocation,
                'cpu_cores': cpu_cores,
                'clone_parent': False,
                'clone_children': [],
                'network_interfaces': {},
                'node': None,
                'available_nodes': available_nodes,
                'lock': LockStates.UNLOCKED.value,
                'graphics_driver': graphics_driver,
                'modifications': [],
                'autostart': AutoStartStates.NO_AUTOSTART.value,
                'uuid': None,
                'agent': {
                    'connection_timeout': None
                },
                'watchdog': {
                    'enabled': False,
                    'interval': None,
                    'reset_fail_count': None,
                    'boot_wait': None
                }
            }

        # Write the configuration to disk
        VirtualMachineConfig._writeJSON(json_data, VirtualMachineConfig.get_config_path(vm_name))

    def _upgrade(self, config):
        """Perform an upgrade of the configuration file"""
        if self._getVersion() < 1:
            # Convert old disk array into hash. Assume that all old disks were
            # local, as Drbd was not supported in pre-version 1 configurations
            config['hard_disks'] = {}
            for disk_id in config['disks']:
                config['hard_disks'][disk_id] = {}
            del config['disks']

            # Set storage type for the VM to local
            config['storage_type'] = 'Local'

            # Set the current node and available nodes to the local machine, as the VM
            # will be local
            config['node'] = get_hostname()
            config['available_nodes'] = [get_hostname()]

            # Obtain details about the VM and add to configuration file
            vm_libvirt_config = self.vm_object.getLibvirtConfig()
            config['memory_allocation'] = vm_libvirt_config.find('./memory').text
            config['cpu_cores'] = vm_libvirt_config.find('./vcpu').text

            # Move network interface configurations into configuration file
            config['network_interfaces'] = {}
            interfaces_xml = vm_libvirt_config.findall('./devices/interface[@type="network"]')
            for interface_xml in interfaces_xml:
                mac_address = interface_xml.find('./mac').get('address')
                connected_network = interface_xml.find('./source').get('network')
                config['network_interfaces'][mac_address] = connected_network

            from mcvirt.virtual_machine.virtual_machine import LockStates
            # Add 'lock' to configuration
            config['lock'] = LockStates.UNLOCKED.value

        if self._getVersion() < 2:
            # Add the hard drive driver configuration to each of the
            # disk configurations
            for disk in config['hard_disks']:
                config['hard_disks'][disk]['driver'] = 'VIRTIO'

        if self._getVersion() < 6:
            config['modifications'] = []
            config['graphics_driver'] = 'vmvga'

        if self._getVersion() < 8:
            config['autostart'] = AutoStartStates.NO_AUTOSTART.value

        if self._getVersion() < 9:
            config['uuid'] = None

        if self._getVersion() < 10:
            if 'volume_group' in config:
                config['custom_volume_group'] = config['volume_group']
                del config['volume_group']

        if self._getVersion() < 12:
            for disk_id in config['hard_disks']:
                if 'storage_backend' in config['hard_disks'][disk_id]:
                    # Generate ID for storage backend
                    name_checksum = hashlib.sha512(
                        config['hard_disks'][disk_id]['storage_backend']).hexdigest()
                    date_checksum = hashlib.sha512('0').hexdigest()
                    storage_id = 'sb-%s-%s' % (name_checksum[0:16], date_checksum[0:24])
                    config['hard_disks'][disk_id]['storage_backend'] = storage_id

        if self._getVersion() < 13:
            users = list(config['permissions']['user'])
            owners = list(config['permissions']['owner'])
            config['permissions'] = {
                'groups': {
                    DEFAULT_USER_GROUP_ID: {
                        'users': users
                    },
                    DEFAULT_OWNER_GROUP_ID: {
                        'users': owners
                    }
                },
                'users': {}
            }

        if self._getVersion() < 14:
            # Create attribute that shows the
            # version of the VM applied to libvirt.
            # i.e. needs registering
            config['applied_version'] = 13
            # Create watchdog config, specifying default to disable
            # and no overrides from global config
            config['agent'] = {
                'connection_timeout': None
            }
            config['watchdog'] = {
                'enabled': False,
                'interval': None,
                'reset_fail_count': None,
                'boot_wait': None
            }

        if self._getVersion() < 15:
            # Convert memory allocation to Bytes from Kib
            config['memory_allocation'] = int(config['memory_allocation']) * 1024
            config['cpu_'] = int(config['cpu_cores'])

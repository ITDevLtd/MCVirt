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

from mcvirt.exceptions import (ConfigFileCouldNotBeFoundException,
                               IntermediateUpgradeRequiredError)
from mcvirt.config.base_subconfig import BaseSubconfig
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.constants import (AutoStartStates,
                              LockStates)
import mcvirt.config.migrations.virtual_machine as migrations


class VirtualMachine(BaseSubconfig):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    SUBTREE_ARRAY = ['virtual_machines']

    def __init__(self, vm_object):
        """Sets member variables"""
        self.vm_object = vm_object
        super(VirtualMachine, self).__init__()

    def _get_config_key(self):
        """Get the key for the config"""
        return self.vm_object.get_id()

    @staticmethod
    def create(vm_id, vm_name, available_nodes, cpu_cores, memory_allocation, graphics_driver):
        """Creates a basic VM configuration for new VMs"""

        # Create basic config
        config = \
            {
                'name': vm_name,
                'version': VirtualMachine.CURRENT_VERSION,
                'applied_version': VirtualMachine.CURRENT_VERSION,
                'permissions':
                {
                    'users': {},
                    'groups': {},
                },
                'hard_drives': {},
                'storage_type': None,
                'delete_protection': False,
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
                'snapshots': [],
                'watchdog': {
                    'enabled': False,
                    'interval': None,
                    'reset_fail_count': None,
                    'boot_wait': None
                }
            }

        # Write the configuration to disk
        VirtualMachine._add_config(
            vm_id, config,
            'Add virtual machine config: %s' % vm_name)

    def _upgrade(self, config):
        """Perform an upgrade of the configuration file"""

        if self._getVersion() < 16:
            raise IntermediateUpgradeRequiredError(
                'Must upgrade to MCVirt v10.0.2 before upgrading to <=v11.0.0')

        if self._getVersion() < 17:
            # Name parameter added in MCVirtConfig object, due to change of VM dir
            migrations.v17.migrate(self, config)

        if self._getVersion() < 21:
            migrations.v21.migrate(self, config)

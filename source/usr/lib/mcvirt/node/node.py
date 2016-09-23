"""Perform configurations for local node."""

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

import Pyro4

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.rpc.lock import MethodLock
from mcvirt.version import VERSION
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.system import System
from mcvirt.constants import DirectoryLocation


class Node(PyroObject):
    """Provides methods to configure the local node."""

    @Expose(locking=True)
    def set_storage_volume_group(self, volume_group):
        """Update the MCVirt configuration to set the volume group for VM storage."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_NODE)

        ArgumentValidator.validate_vg_name(volume_group)

        # Update global MCVirt configuration
        def update_config(config):
            config['vm_storage_vg'] = volume_group
        mcvirt_config = MCVirtConfig()
        mcvirt_config.update_config(update_config,
                                    'Set virtual machine storage volume group to %s' %
                                    volume_group)

    @Expose(locking=True)
    def set_cluster_ip_address(self, ip_address):
        """Update the cluster IP address for the node."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_NODE)

        ArgumentValidator.validate_ip_address(ip_address)

        # Update global MCVirt configuration
        def update_config(config):
            config['cluster']['cluster_ip'] = ip_address
        mcvirt_config = MCVirtConfig()
        mcvirt_config.update_config(update_config, 'Set node cluster IP address to %s' %
                                                   ip_address)

    def get_free_vg_space(self):
        """Returns the free space in megabytes."""
        _, out, err = System.runCommand(['vgs', MCVirtConfig().get_config()['vm_storage_vg'],
                                         '-o', 'free', '--noheadings', '--nosuffix', '--units',
                                         'm'], False,
                                        DirectoryLocation.BASE_STORAGE_DIR)
        return float(out)

    def is_volume_group_set(self):
        """Determine if the volume group has been configured on the node"""
        return bool(MCVirtConfig().get_config()['vm_storage_vg'])

    def volume_group_exists(self):
        """Determine if the volume group actually exists on the node."""
        _, out, err = System.runCommand(['vgs', '|', 'grep',
                                         MCVirtConfig().get_config()['vm_storage_vg']],
                                        False, DirectoryLocation.BASE_STORAGE_DIR)
        return bool(out)

    @Expose()
    def get_version(self):
        """Return the version of the running daemon"""
        return VERSION

    @Expose()
    def clear_method_lock(self):
        """Force clear a method lock to escape deadlock"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SUPERUSER)
        lock = MethodLock.get_lock()
        if lock.locked():
            lock.release()
            Pyro4.current_context.has_lock = False
            return True
        return False

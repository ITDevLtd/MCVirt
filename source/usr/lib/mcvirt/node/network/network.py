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

import xml.etree.ElementTree as ET
import Pyro4

from mcvirt.mcvirt import MCVirtException
from mcvirt.auth.auth import Auth
from mcvirt.rpc.lock import lockingMethod


class NetworkDoesNotExistException(MCVirtException):
    """Network does not exist"""
    pass


class NetworkUtilizedException(MCVirtException):
    """Network is utilized by virtual machines"""
    pass


class Network(object):
    """Provides an interface to LibVirt networks"""

    def __init__(self, mcvirt_instance, name):
        """Sets member variables and obtains libvirt domain object"""
        self.mcvirt_instance = mcvirt_instance
        self.name = name

        # Ensure network exists
        if not self._checkExists(name):
            raise NetworkDoesNotExistException('Network does not exist: %s' % name)

    @staticmethod
    def getNetworkConfig():
        """Returns the network configuration for the node"""
        from mcvirt.mcvirt_config import MCVirtConfig
        mcvirt_config = MCVirtConfig().getConfig()
        return mcvirt_config['networks']

    @Pyro4.expose()
    @lockingMethod()
    def delete(self):
        """Deletes a network from the node"""
        # Ensure user has permission to manage networks
        self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

        # Ensure network is not connected to any VMs
        connected_vms = self._getConnectedVirtualMachines()
        if len(connected_vms):
            connected_vm_name_string = ', '.join(vm.getName() for vm in connected_vms)
            raise NetworkUtilizedException(
                'Network \'%s\' cannot be removed as it is used by the following VMs: %s' %
                (self.getName(), connected_vm_name_string))

        # Undefine object from libvirt
        try:
            self._getLibVirtObject().destroy()
            self._getLibVirtObject().undefine()
        except:
            raise MCVirtException('Failed to delete network from libvirt')

        if self.mcvirt_instance.initialiseNodes():
            # Update nodes
            from mcvirt.cluster.cluster import Cluster
            cluster = Cluster(self.mcvirt_instance)
            cluster.runRemoteCommand('node-network-delete', {'network_name': self.getName()})

        # Update MCVirt config
        def updateConfig(config):
            del config['networks'][self.getName()]
        from mcvirt.mcvirt_config import MCVirtConfig
        MCVirtConfig().updateConfig(updateConfig, 'Deleted network \'%s\'' % self.getName())

    def _getConnectedVirtualMachines(self):
        """Returns an array of VM objects that have an interface connected to the network"""
        connected_vms = []

        # Iterate over all VMs and determine if any use the network to be deleted
        all_vm_objects = self.mcvirt_instance.getAllVirtualMachineObjects()
        for vm_object in all_vm_objects:

            # Iterate over each network interface for the VM and determine if it
            # is connected to this network
            all_vm_interfaces = vm_object.getNetworkObjects()
            contains_connected_interface = False
            for network_interface in all_vm_interfaces:
                if network_interface.getConnectedNetwork() == self.getName():
                    contains_connected_interface = True

            # If the VM contains at least one interface connected to the network,
            # add it to the array to be returned
            if contains_connected_interface:
                connected_vms.append(vm_object)

        # Return array of VMs that use this network
        return connected_vms

    def _getLibVirtObject(self):
        """Returns the LibVirt object for the network"""
        return self.mcvirt_instance.getLibvirtConnection().networkLookupByName(self.name)

    @Pyro4.expose()
    def getName(self):
        """Returns the name of the network"""
        return self.name

    def getAdapter(self):
        """Returns the name of the physical bridge adapter for the network"""
        return Network.getNetworkConfig()[self.getName()]

    @staticmethod
    def _checkExists(name):
        """Check if a network exists"""
        # Obtain array of all networks from libvirt
        networks = Network.getNetworkConfig()

        # Determine if the name of any of the networks returned
        # matches the requested name
        return (name in networks.keys())

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

from mcvirt.mcvirt import MCVirtException
from mcvirt.auth import Auth

import xml.etree.ElementTree as ET


class NetworkDoesNotExistException(MCVirtException):

    """Network does not exist"""
    pass


class NetworkAlreadyExistsException(MCVirtException):

    """Network already exists with the same name"""
    pass


class NetworkUtilizedException(MCVirtException):

    """Network is utilized by virtual machines"""
    pass


class Network:

    """Provides an interface to LibVirt networks"""

    def __init__(self, mcvirt_object, name):
        """Sets member variables and obtains libvirt domain object"""
        self.mcvirt_object = mcvirt_object
        self.name = name

        # Ensure network exists
        if (not self._checkExists(name)):
            raise NetworkDoesNotExistException('Network does not exist: %s' % name)

    @staticmethod
    def getConfig():
        """Returns the network configuration for the node"""
        from mcvirt.mcvirt_config import MCVirtConfig
        mcvirt_config = MCVirtConfig().getConfig()
        return mcvirt_config['networks']

    def delete(self):
        """Deletes a network from the node"""
        # Ensure user has permission to manage networks
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

        # Ensure network is not connected to any VMs
        connected_vms = self._checkConnectedVirtualMachines()
        if (len(connected_vms)):
            connected_vm_name_string = ', '.join(vm.getName() for vm in connected_vms)
            raise NetworkUtilizedException(
                'Network \'%s\' cannot be removed as it is used by the following VMs: %s' %
                (self.getName(), connected_vm_name_string))

        # Undefine object from libvirt
        try:
            self._getLibVirtObject().undefine()
        except:
            raise MCVirtException('Failed to delete network from libvirt')

        if (self.mcvirt_object.initialiseNodes()):
            # Update nodes
            from mcvirt.cluster.cluster import Cluster
            cluster = Cluster(self.mcvirt_object)
            cluster.runRemoteCommand('node-network-delete', {'network_name': self.getName()})

        # Update MCVirt config
        def updateConfig(config):
            del config['networks'][self.getName()]
        from mcvirt.mcvirt_config import MCVirtConfig
        MCVirtConfig().updateConfig(updateConfig, 'Deleted network \'%s\'' % self.getName())

    def _checkConnectedVirtualMachines(self):
        """Returns an array of VM objects that have an interface connected to the network"""
        connected_vms = []

        # Iterate over all VMs and determine if any use the network to be deleted
        all_vm_objects = self.mcvirt_object.getAllVirtualMachineObjects()
        for vm_object in all_vm_objects:

            # Iterate over each network interface for the VM and determine if it
            # is connected to this network
            all_vm_interfaces = vm_object.getNetworkObjects()
            contains_connected_interface = False
            for network_interface in all_vm_interfaces:
                if (network_interface.getConnectedNetwork() == self.getName()):
                    contains_connected_interface = True

            # If the VM contains at least one interface connected to the network,
            # add it to the array to be returned
            if (contains_connected_interface):
                connected_vms.append(vm_object)

        # Return array of VMs that use this network
        return connected_vms

    def _getLibVirtObject(self):
        """Returns the LibVirt object for the network"""
        return self.mcvirt_object.getLibvirtConnection().networkLookupByName(self.name)

    def getName(self):
        """Returns the name of the network"""
        return self.name

    @staticmethod
    def _checkExists(name):
        """Check if a network exists"""
        # Obtain array of all networks from libvirt
        networks = Network.getConfig()

        # Determine if the name of any of the networks returned
        # matches the requested name
        return (name in networks.keys())

    @staticmethod
    def create(mcvirt_object, name, physical_interface):
        """Creates a network on the node"""
        # Ensure user has permission to manage networks
        mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

        # Ensure network does not already exist
        if (Network._checkExists(name)):
            raise NetworkAlreadyExistsException('Network already exists: %s' % name)

        # Create XML for network
        network_xml = ET.Element('network')
        network_xml.set('ipv6', 'no')
        network_name_xml = ET.SubElement(network_xml, 'name')
        network_name_xml.text = name

        # Create 'forward'
        network_forward_xml = ET.SubElement(network_xml, 'forward')
        network_forward_xml.set('mode', 'bridge')

        # Set interface bridge
        network_bridge_xml = ET.SubElement(network_xml, 'bridge')
        network_bridge_xml.set('name', physical_interface)

        # Convert XML object to string
        network_xml_string = ET.tostring(network_xml, encoding='utf8', method='xml')

        # Attempt to register network with LibVirt
        try:
            mcvirt_object.getLibvirtConnection().networkDefineXML(network_xml_string)
        except:
            raise MCVirtException('An error occurred whilst registering network with LibVirt')

        if (mcvirt_object.initialiseNodes()):
            # Update nodes
            from mcvirt.cluster.cluster import Cluster
            cluster = Cluster(mcvirt_object)
            cluster.runRemoteCommand('node-network-create',
                                     {'network_name': name,
                                      'physical_interface': physical_interface})

        # Update MCVirt config
        def updateConfig(config):
            config['networks'][name] = physical_interface
        from mcvirt.mcvirt_config import MCVirtConfig
        MCVirtConfig().updateConfig(updateConfig, 'Created network \'%s\'' % name)

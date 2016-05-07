# Copyright (c) 2016 - I.T. Dev Ltd
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
from texttable import Texttable
import xml.etree.ElementTree as ET

from mcvirt.mcvirt import MCVirtException
from mcvirt.auth.auth import Auth
from mcvirt.node.network.network import Network


class NetworkAlreadyExistsException(MCVirtException):
    """Network already exists with the same name"""
    pass


class Factory(object):
    """Class for obtaining network objects"""

    OBJECT_TYPE = 'network'

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    def create(self, name, physical_interface):
        """Creates a network on the node"""
        # Ensure user has permission to manage networks
        Auth().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

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
            self.mcvirt_instance.getLibvirtConnection().networkDefineXML(network_xml_string)
        except:
            raise MCVirtException('An error occurred whilst registering network with LibVirt')

        if (self.mcvirt_instance.initialiseNodes()):
            # Update nodes
            from mcvirt.cluster.cluster import Cluster
            cluster = Cluster(self.mcvirt_instance)
            cluster.runRemoteCommand('node-network-create',
                                     {'network_name': name,
                                      'physical_interface': physical_interface})

        # Update MCVirt config
        def updateConfig(config):
            config['networks'][name] = physical_interface
        from mcvirt.mcvirt_config import MCVirtConfig
        MCVirtConfig().updateConfig(updateConfig, 'Created network \'%s\'' % name)

        # Obtain instance of the network object
        network_instance = self.getNetworkByName(name)

        # Start network
        network_instance._getLibVirtObject().create()

        # Set network to autostart
        network_instance._getLibVirtObject().setAutostart(True)

    @Pyro4.expose()
    def getNetworkByName(self, network_name):
        network_object = Network(self.mcvirt_instance, network_name)
        if '_pyroDaemon' in self.__dict__:
            self._pyroDaemon.register(network_object)
        return network_object

    def getAllNetworkNames(self):
        """Returns a list of network names"""
        return Network.getNetworkConfig().keys()

    def getAllNetworkObjects(self):
        """Returns all network objects"""
        network_objects = []
        for network_name in self.getAllNetworkNames():
            network_objects.append(self.getNetworkByName(network_name))

        return network_objects

    @Pyro4.expose()
    def getNetworkListTable(self):
        """Return a table of networks registered on the node"""
        # Create table and set headings
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Network', 'Physical Interface'))

        # Obtain network configurations and add to table
        for network_object in self.getAllNetworkObjects():
            table.add_row((network_object.getName(), network_object.getAdapter()))
        return table.draw()

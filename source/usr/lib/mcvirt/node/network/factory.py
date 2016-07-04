"""Provide class for generating network objects"""

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
import netifaces

from mcvirt.exceptions import (NetworkAlreadyExistsException, LibvirtException,
                               InterfaceDoesNotExist, NetworkDoesNotExistException)
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.node.network.network import Network
from mcvirt.rpc.lock import locking_method
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.argument_validator import ArgumentValidator


class Factory(PyroObject):
    """Class for obtaining network objects"""

    OBJECT_TYPE = 'network'

    @Pyro4.expose()
    def interface_exists(self, interface):
        """Public method for to determine if an interface exists"""
        self._get_registered_object('auth').assert_user_type('ConnectionUser', 'ClusterUser')
        return self._interface_exists(interface)

    def _interface_exists(self, interface):
        """Determine if a given network adapter exists on the node"""
        if interface not in netifaces.interfaces():
            return False

        addr = netifaces.ifaddresses(interface)
        return (netifaces.AF_INET in addr)

    @Pyro4.expose()
    @locking_method()
    def create(self, name, physical_interface):
        """Create a network on the node"""
        # Ensure user has permission to manage networks
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_HOST_NETWORKS)

        # Validate name
        ArgumentValidator.validate_network_name(name)

        # Ensure network does not already exist
        if self.check_exists(name):
            raise NetworkAlreadyExistsException('Network already exists: %s' % name)

        # Ensure that the physical interface eixsts
        if not self._interface_exists(physical_interface):
            raise InterfaceDoesNotExist(
                'Physical interface %s does not exist' % physical_interface
            )

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
            self._get_registered_object('libvirt_connector').get_connection(
            ).networkDefineXML(network_xml_string)
        except:
            raise LibvirtException('An error occurred whilst registering network with LibVirt')

        # Update MCVirt config
        def update_config(config):
            config['networks'][name] = physical_interface
        from mcvirt.mcvirt_config import MCVirtConfig
        MCVirtConfig().update_config(update_config, 'Created network \'%s\'' % name)

        # Obtain instance of the network object
        network_instance = self.get_network_by_name(name)

        # Start network
        network_instance._get_libvirt_object().create()

        # Set network to autostart
        network_instance._get_libvirt_object().setAutostart(True)

        if self._is_cluster_master:
            def remote_add(node):
                network_factory = node.get_connection('network_factory')
                network_factory.create(name, physical_interface)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_add)

        return network_instance

    @Pyro4.expose()
    def get_network_by_name(self, network_name):
        """Return a network object of the network for a given name."""
        self.ensure_exists(network_name)
        network_object = Network(network_name)
        self._register_object(network_object)
        return network_object

    @Pyro4.expose()
    def get_all_network_names(self):
        """Return a list of network names"""
        return Network.get_network_config().keys()

    @Pyro4.expose()
    def get_all_network_objects(self):
        """Return all network objects"""
        network_objects = []
        for network_name in self.get_all_network_names():
            network_objects.append(self.get_network_by_name(network_name))
        return network_objects

    @Pyro4.expose()
    def get_network_list_table(self):
        """Return a table of networks registered on the node"""
        # Create table and set headings
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Network', 'Physical Interface'))

        # Obtain network configurations and add to table
        for network_object in self.get_all_network_objects():
            table.add_row((network_object.get_name(), network_object.get_adapter()))
        return table.draw()

    def ensure_exists(self, name):
        """Ensure network exists"""
        if not self.check_exists(name):
            raise NetworkDoesNotExistException('Network does not exist: %s' % name)

    @Pyro4.expose()
    def check_exists(self, name):
        """Check if a network exists"""
        # Obtain array of all networks from libvirt
        networks = Network.get_network_config()

        # Determine if the name of any of the networks returned
        # matches the requested name
        return (name in networks.keys())

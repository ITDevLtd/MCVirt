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

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import locking_method
from network_adapter import NetworkAdapter
from mcvirt.auth.permissions import PERMISSIONS


class Factory(PyroObject):
    """Factory method to create/obtain network adapter instances"""

    OBJECT_TYPE = 'network adapter'
    NETWORK_ADAPTER_CLASS = NetworkAdapter

    @Pyro4.expose()
    @locking_method()
    def create(self, virtual_machine, network_object, mac_address=None):
        """Create a network interface for the local VM"""
        virtual_machine = self._convert_remote_object(virtual_machine)
        network_object = self._convert_remote_object(network_object)
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, virtual_machine
        )

        # Generate a MAC address, if one has not been supplied
        if (mac_address is None):
            mac_address = NetworkAdapter.generateMacAddress()

        # Add network interface to VM configuration
        def update_vm_config(config):
            config['network_interfaces'][mac_address] = network_object.get_name()
        virtual_machine.get_config_object().update_config(
            update_vm_config, 'Added network adapter to \'%s\' on \'%s\' network' %
            (virtual_machine.get_name(), network_object.get_name()))

        if self._is_cluster_master:
            def remote_command(node_connection):
                remote_vm_factory = node_connection.get_connection('virtual_machine_factory')
                remote_vm = remote_vm_factory.getVirtualMachineByName(virtual_machine.get_name())
                remote_network_factory = node_connection.get_connection('network_factory')
                remote_network = remote_network_factory.get_network_by_name(
                    network_object.get_name()
                )
                remote_network_adapter_factory = node_connection.get_connection(
                    'network_adapter_factory')
                remote_network_adapter_factory.create(
                    remote_vm, remote_network, mac_address=mac_address)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

        network_adapter_object = self.getNetworkAdapterByMacAdress(virtual_machine, mac_address)

        # Only update the LibVirt configuration if VM is registered on this node
        if virtual_machine.isRegisteredLocally():
            def updateXML(domain_xml):
                network_xml = network_adapter_object._generateLibvirtXml()
                device_xml = domain_xml.find('./devices')
                device_xml.append(network_xml)

            virtual_machine._editConfig(updateXML)
        return network_adapter_object

    @Pyro4.expose()
    def getNetworkAdaptersByVirtualMachine(self, virtual_machine):
        """Returns an array of network interface objects for each of the
        interfaces attached to the VM"""
        interfaces = []
        virtual_machine = self._convert_remote_object(virtual_machine)
        vm_config = virtual_machine.get_config_object().get_config()
        for mac_address in vm_config['network_interfaces'].keys():
            interface_object = NetworkAdapter(mac_address, virtual_machine)
            self._register_object(interface_object)
            interfaces.append(interface_object)
        return interfaces

    @Pyro4.expose()
    def getNetworkAdapterByMacAdress(self, virtual_machine, mac_address):
        """Returns the network adapter by a given MAC address"""
        # Ensure that MAC address is a valid network adapter for the VM
        virtual_machine = self._convert_remote_object(virtual_machine)
        interface_object = NetworkAdapter(mac_address, virtual_machine)
        self._register_object(interface_object)
        return interface_object

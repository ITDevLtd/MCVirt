"""Provide interface to libvirt network objects."""

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

from mcvirt.exceptions import (LibvirtException, NetworkUtilizedException,
                               NetworkNotAvailableOnNodeError)
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import get_hostname
from mcvirt.config.core import Core as MCVirtConfig


class Network(PyroObject):
    """Provides an interface to LibVirt networks."""

    def __init__(self, name):
        """Set member variables and obtains libvirt domain object."""
        self.name = name

    @staticmethod
    def get_network_config():
        """Return the network configuration for the node."""
        mcvirt_config = MCVirtConfig().get_config()
        return mcvirt_config['networks']

    @property
    def nodes(self):
        """Return the nodes that the network is available to."""
        # Since networks are currently global, obtain all nodes
        return self._get_registered_object('cluster').get_nodes(return_all=True,
                                                                include_local=True)

    @Expose(locking=True)
    def delete(self):
        """Delete a network from the node."""
        # Ensure user has permission to manage networks
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_HOST_NETWORKS)

        # Ensure network is not connected to any VMs
        connected_vms = self._get_connected_virtual_machines()
        if len(connected_vms):
            connected_vm_name_string = ', '.join(vm.get_name() for vm in connected_vms)
            raise NetworkUtilizedException(
                'Network \'%s\' cannot be removed as it is used by the following VMs: %s' %
                (self.get_name(), connected_vm_name_string))

        # Undefine object from libvirt
        try:
            self._get_libvirt_object().destroy()
            self._get_libvirt_object().undefine()
        except Exception:
            raise LibvirtException('Failed to delete network from libvirt')

        # Update MCVirt config
        def update_config(config):
            """Delete network from MCVirt config."""
            del config['networks'][self.get_name()]
        MCVirtConfig().update_config(update_config, 'Deleted network \'%s\'' % self.get_name())

        if self._is_cluster_master:
            def remove_remote(node):
                """Remove network from remote nodes."""
                network_factory = node.get_connection('network_factory')
                network = network_factory.get_network_by_name(self.name)
                node.annotate_object(network)
                network.delete()
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remove_remote)

    def _get_connected_virtual_machines(self):
        """Return an array of VM objects that have an interface connected to the network."""
        connected_vms = []

        # Iterate over all VMs and determine if any use the network to be deleted
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        for vm_object in virtual_machine_factory.get_all_virtual_machines():

            # Iterate over each network interface for the VM and determine if it
            # is connected to this network
            network_adapter_factory = self._get_registered_object('network_adapter_factory')
            all_vm_interfaces = network_adapter_factory.getNetworkAdaptersByVirtualMachine(
                vm_object)
            contains_connected_interface = False
            for network_interface in all_vm_interfaces:
                if network_interface.getConnectedNetwork() == self.get_name():
                    contains_connected_interface = True

            # If the VM contains at least one interface connected to the network,
            # add it to the array to be returned
            if contains_connected_interface:
                connected_vms.append(vm_object)

        # Return array of VMs that use this network
        return connected_vms

    def _get_libvirt_object(self):
        """Return the LibVirt object for the network."""
        return self._get_registered_object(
            'libvirt_connector'
        ).get_connection().networkLookupByName(self.name)

    @Expose()
    def get_name(self):
        """Return the name of the network."""
        return self.name

    @Expose()
    def get_adapter(self):
        """Return the name of the physical bridge adapter for the network."""
        return Network.get_network_config()[self.get_name()]

    def check_available_on_node(self, node=None):
        """Determine whether network is available on a given node."""
        # Default to local node
        if node is None:
            node = get_hostname()
        return node in self.nodes

    def ensure_available_on_node(self, node=None):
        """Ensure that network is available on a given node."""
        # Default to local node
        if node is None:
            node = self._get_registered_object('cluster').get_hostname()

        # Check if it's available and raise an exception is it's not available
        if not self.check_available_on_node(node=node):
            raise NetworkNotAvailableOnNodeError(
                'Network \'%s\' is not available on node \'%s\'' %
                (self.get_name(), node)
            )

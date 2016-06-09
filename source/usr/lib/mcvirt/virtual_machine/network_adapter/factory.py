import Pyro4

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import lockingMethod
from network_adapter import NetworkAdapter
from mcvirt.auth.permissions import PERMISSIONS

class Factory(PyroObject):
    """Factory method to create/obtain network adapter instances"""

    OBJECT_TYPE = 'network adapter'

    def __init__(self, mcvirt_instance):
        """Store member variables"""
        self.mcvirt_instance = mcvirt_instance

    @Pyro4.expose()
    @lockingMethod()
    def create(self, virtual_machine, network_object, mac_address=None):
        """Creates a network interface for the local VM"""
        virtual_machine = self._convert_remote_object(virtual_machine)
        network_object = self._convert_remote_object(network_object)
        self._get_registered_object('auth').assertPermission(
            PERMISSIONS.MODIFY_VM, virtual_machine
        )

        # Generate a MAC address, if one has not been supplied
        if (mac_address is None):
            mac_address = NetworkAdapter.generateMacAddress()

        # Add network interface to VM configuration
        def updateVmConfig(config):
            config['network_interfaces'][mac_address] = network_object.getName()
        virtual_machine.getConfigObject().updateConfig(
            updateVmConfig, 'Added network adapter to \'%s\' on \'%s\' network' %
            (virtual_machine.getName(), network_object.getName()))

        if self._is_cluster_master:
            def remote_command(node_connection):
                remote_vm_factory = node_connection.getConnection('virtual_machine_factory')
                remote_vm = remote_vm_factory.getVirtualMachineByName(virtual_machine.getName())
                remote_network_factory = node_connection.getConnection('network_factory')
                remote_network = remote_network_factory.getNetworkByName(network_object.getName())
                remote_network_adapter_factory = node_connection.getConnection('network_adapter_factory')
                remote_network_adapter_factory.create(remote_vm, remote_network, mac_address=mac_address)
            cluster = self._get_registered_object('cluster')
            cluster.runRemoteCommand(remote_command)


        network_adapter_object = self.getNetworkAdapterByMacAdress(virtual_machine, mac_address)

        # Only update the LibVirt configuration if VM is registered on this node
        if virtual_machine.isRegisteredLocally():
            def updateXML(domain_xml):
                network_xml = network_adapter_object._generateLibvirtXml()
                device_xml = domain_xml.find('./devices')
                device_xml.append(network_xml)

            virtual_machine.editConfig(updateXML)
        return network_adapter_object

    @Pyro4.expose()
    def getNetworkAdaptersByVirtualMachine(self, virtual_machine):
        """Returns an array of network interface objects for each of the
        interfaces attached to the VM"""
        interfaces = []
        vm_config = virtual_machine.getConfigObject().getConfig()
        for mac_address in vm_config['network_interfaces'].keys():
            interface_object = NetworkAdapter(mac_address, virtual_machine)
            self._register_object(interface_object)
            interfaces.append(interface_object)
        return interfaces

    @Pyro4.expose()
    def getNetworkAdapterByMacAdress(self, virtual_machine, mac_address):
        """Returns the network adapter by a given MAC address"""
        # Ensure that MAC address is a valid network adapter for the VM
        interface_object = NetworkAdapter(mac_address, virtual_machine)
        self._register_object(interface_object)
        return interface_object

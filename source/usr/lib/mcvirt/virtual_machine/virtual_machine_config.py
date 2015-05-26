#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

from mcvirt.mcvirt import MCVirtException
from mcvirt.config_file import ConfigFile

class VirtualMachineConfig(ConfigFile):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    def __init__(self, vm_object):
        """Sets member variables and obtains libvirt domain object"""
        self.git_object = None
        self.vm_object = vm_object
        self.config_file = VirtualMachineConfig.getConfigPath(self.vm_object.name)
        if (not os.path.isfile(self.config_file)):
            raise MCVirtException('Could not find config file for %s' % vm_object.name)

        # Perform upgrade of configuration
        self.upgrade(vm_object.mcvirt_object)

    @staticmethod
    def getConfigPath(vm_name):
        """Provides the path of the VM-spefic configuration file"""
        from mcvirt.virtual_machine.virtual_machine import VirtualMachine
        return ('%s/config.json' % VirtualMachine.getVMDir(vm_name))

    @staticmethod
    def create(vm_name, available_nodes, cpu_cores, memory_allocation):
        """Creates a basic VM configuration for new VMs"""
        from mcvirt.virtual_machine.virtual_machine import VirtualMachine, LockStates
        from mcvirt.cluster.cluster import Cluster

        # Create basic config
        json_data = \
          {
            'version': VirtualMachineConfig.CURRENT_VERSION,
            'permissions':
            {
              'user': [],
              'owner': [],
            },
            'hard_disks': {},
            'storage_type': None,
            'memory_allocation': str(memory_allocation),
            'cpu_cores': str(cpu_cores),
            'clone_parent': False,
            'clone_children': [],
            'network_interfaces': {},
            'node': None,
            'available_nodes': available_nodes,
            'lock': LockStates.UNLOCKED.value
          }

        # Write the configuration to disk
        VirtualMachineConfig._writeJSON(json_data, VirtualMachineConfig.getConfigPath(vm_name))

    def _upgrade(self, mcvirt_instance, config):
        """Perform an upgrade of the configuration file"""
        if (self._getVersion() < 1):
            # Convert old disk array into hash. Assume that all old disks were
            # local, as DRBD was not supported in pre-version 1 configurations
            config['hard_disks'] = {}
            for disk_id in config['disks']:
                config['hard_disks'][disk_id] = {}
            del(config['disks'])

            # Set storage type for the VM to local
            config['storage_type'] = 'Local'

            # Set the current node and available nodes to the local machine, as the VM
            # will be local
            from mcvirt.cluster.cluster import Cluster
            config['node'] = Cluster.getHostname()
            config['available_nodes'] = [Cluster.getHostname()]

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

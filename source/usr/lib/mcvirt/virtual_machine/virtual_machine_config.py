#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

from mcvirt.mcvirt import McVirtException
from mcvirt.config_file import ConfigFile

class VirtualMachineConfig(ConfigFile):
  """Provides operations to obtain and set the McVirt configuration for a VM"""

  def __init__(self, vm_object):
    """Sets member variables and obtains libvirt domain object"""
    self.vm_object = vm_object
    self.config_file = VirtualMachineConfig.getConfigPath(self.vm_object.name)
    if (not os.path.isfile(self.config_file)):
      raise McVirtException('Could not find config file for %s' % vm_object.name)

  @staticmethod
  def getConfigPath(vm_name):
    """Provides the path of the VM-spefic configuration file"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    return ('%s/config.json' % VirtualMachine.getVMDir(vm_name))

  @staticmethod
  def create(vm_name, node, available_nodes, cpu_cores, memory_allocation):
    """Creates a basic VM configuration for new VMs"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    from mcvirt.cluster.cluster import Cluster

    # Create basic config
    json_data = \
      {
        'permissions':
        {
          'user': [],
          'owner': [],
        },
        'disks': [],
        'memory_allocation': str(memory_allocation),
        'cpu_cores': str(cpu_cores),
        'clone_parent': False,
        'clone_children': [],
        'network_interfaces': {},
        'node': node,
        'available_nodes': available_nodes
      }

    # Write the configuration to disk
    VirtualMachineConfig.writeJSON(json_data, VirtualMachineConfig.getConfigPath(vm_name))
#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

from mcvirt.mcvirt import McVirtException

class Config:
  """Provides operations to obtain and set the McVirt configuration for a VM"""

  def __init__(self, vm_object):
    """Sets member variables and obtains libvirt domain object"""
    self.vm_object = vm_object

    if (not os.path.isfile(Config.getConfigPath(self.vm_object.name))):
      raise McVirtException('Could not find config file for %s' % vm_object.name)


  @staticmethod
  def getConfigPath(vm_name):
    """Provides the path of the VM-spefic configuration file"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    return ('%s/config.json' % VirtualMachine.getVMDir(vm_name))


  def getConfig(self):
    """Loads the VM configuration from disk and returns the parsed JSON"""
    config_file = open(Config.getConfigPath(self.vm_object.name), 'r')
    config = json.loads(config_file.read())
    config_file.close()
    return config


  def updateConfig(self, config):
    """Writes a provided configuration back to the configuration file"""
    Config.writeJSON(config, Config.getConfigPath(self.vm_object.name))
    self.config = config


  @staticmethod
  def writeJSON(data, file_name):
    """Parses and writes the JSON VM config file"""
    json_data = json.dumps(data, indent = 2, separators = (',', ': '))

    # Open the config file and write to contents
    config_file = open(file_name, 'w')
    config_file.write(json_data)
    config_file.close()


  @staticmethod
  def create(vm_name):
    """Creates a basic VM configuration for new VMs"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine

    # Create basic config
    json_data = \
      {
        'disks': []
      }

    # Write the configuration to disk
    Config.writeJSON(json_data, Config.getConfigPath(vm_name))
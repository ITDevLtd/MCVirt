#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

class ConfigFile():
  """Provides operations to obtain and set the McVirt configuration for a VM"""

  def __init__(self):
    """Sets member variables and obtains libvirt domain object"""
    raise NotImplementedError


  @staticmethod
  def getConfigPath(vm_name):
    """Provides the path of the VM-spefic configuration file"""
    raise NotImplementedError


  def getConfig(self):
    """Loads the VM configuration from disk and returns the parsed JSON"""
    config_file = open(self.config_file, 'r')
    config = json.loads(config_file.read())
    config_file.close()
    return config


  def updateConfig(self, callback_function):
    """Writes a provided configuration back to the configuration file"""
    config = self.getConfig()
    callback_function(config)
    ConfigFile.writeJSON(config, self.config_file)
    self.config = config


  def getPermissionConfig(self):
    config = self.getConfig()
    return config['permissions']


  @staticmethod
  def writeJSON(data, file_name):
    """Parses and writes the JSON VM config file"""
    json_data = json.dumps(data, indent = 2, separators = (',', ': '))

    # Open the config file and write to contents
    config_file = open(file_name, 'w')
    config_file.write(json_data)
    config_file.close()


  @staticmethod
  def create(self):
    """Creates a basic VM configuration for new VMs"""
    raise NotImplementedError
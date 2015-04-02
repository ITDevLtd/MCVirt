#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

from config_file import ConfigFile

class McVirtConfig(ConfigFile):
  """Provides operations to obtain and set the McVirt configuration for a VM"""

  def __init__(self):
    """Sets member variables and obtains libvirt domain object"""
    from mcvirt import McVirt
    self.config_file = McVirt.BASE_STORAGE_DIR + '/config.json'
    if (not os.path.isfile(self.config_file)):
      self.create()

  def create(self):
    """Creates a basic VM configuration for new VMs"""

    # Create basic config
    json_data = \
    {
      'superusers': [],
      'permissions':
      {
        'user': [],
        'owner': [],
      },
      'vm_storage_vg': '',
      'cluster': \
      {
        'cluster_ip': '',
        'nodes': {}
      },
      'virtual_machines': [],
      'networks': [],
      'drbd': \
      {
        'secret': '',
        'sync_rate': '10M',
        'protocol': 'C'
      }
    }

    # Write the configuration to disk
    McVirtConfig.writeJSON(json_data, self.config_file)

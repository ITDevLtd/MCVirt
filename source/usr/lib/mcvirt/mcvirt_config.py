#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
import os

from config_file import ConfigFile

class McVirtConfig(ConfigFile):
  """Provides operations to obtain and set the McVirt configuration for a VM"""

  def __init__(self, mcvirt_instance=None, perform_upgrade=False):
    """Sets member variables and obtains libvirt domain object"""
    from mcvirt import McVirt

    self.config_file = McVirt.NODE_STORAGE_DIR + '/config.json'

    if (not os.path.isdir(McVirt.NODE_STORAGE_DIR)):
      self._createConfigDirectories()

    if (not os.path.isfile(self.config_file)):
      self.create()

    # If performing an upgrade has been specified, do so
    if (perform_upgrade and mcvirt_instance):
      self.upgrade(mcvirt_instance)

  def _createConfigDirectories(self):
    """Creates the configuration directories for the node"""
    # Initialise the git repository
    from mcvirt import McVirt
    import pwd

    os.mkdir(McVirt.NODE_STORAGE_DIR)
    os.mkdir(McVirt.BASE_VM_STORAGE_DIR)
    os.mkdir(McVirt.ISO_STORAGE_DIR)

    # Set permission on McVirt directory
    os.chmod(McVirt.BASE_STORAGE_DIR, 0600)
    os.chown(McVirt.BASE_STORAGE_DIR, pwd.getpwnam('libvirt-qemu').pw_uid, 0)

  def create(self):
    """Creates a basic VM configuration for new VMs"""
    from node.drbd import DRBD as NodeDRBD

    # Create basic config
    json_data = \
    {
      'version': self.CURRENT_VERSION,
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
      'networks': {},
      'drbd': NodeDRBD.getDefaultConfig(),
      'git':
      {
        'repo_domain': '',
        'repo_path': '',
        'repo_protocol': '',
        'username': '',
        'password': '',
        'commit_name': '',
        'commit_email': ''
      }
    }

    # Write the configuration to disk
    McVirtConfig._writeJSON(json_data, self.config_file)

  def _upgrade(self, mcvirt_instance, config):
    """Perform an upgrade of the configuration file"""
    if (self._getVersion() < 1):
      # Add new global permission groups
      for new_permission_goup in ['user', 'owner']:
        if (new_permission_goup not in config['permissions'].keys()):
          config['permissions'][new_permission_goup] = []

      # Add cluster configuration to config
      config['cluster'] = \
      {
        'cluster_ip': '',
        'nodes': {}
      }

      # Obtain list of virtual machines from LibVirt
      all_domains = mcvirt_instance.getLibvirtConnection().listAllDomains()

      # Add virtual machines to global configuration
      config['virtual_machines'] = [vm.name() for vm in all_domains]

      # Obtain list of networks from LibVirt
      all_networks = mcvirt_instance.getLibvirtConnection().listAllNetworks()
      config['networks'] = {}
      for network in all_networks:
        config['networks'][network.name()] = network.bridgeName()

      # Add default DRBD configuration
      config['drbd'] = \
      {
        'enabled': 0,
        'secret': '',
        'sync_rate': '10M',
        'protocol': 'C'
      }

      # Create git configuration
      config['git'] = \
      {
        'repo_domain': '',
        'repo_path': '',
        'repo_protocol': '',
        'username': '',
        'password': '',
        'commit_name': '',
        'commit_email': ''
      }

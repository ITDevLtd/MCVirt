#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import os

from mcvirt.virtual_machine.hard_drive.config.base import Base
from mcvirt.node.drbd import DRBD as NodeDRBD
from mcvirt.mcvirt import McVirt
from mcvirt.system import System

class DRBD(Base):
  """Provides a configuration interface for DRBD-based hard drive objects"""

  MAXIMUM_DEVICES = 1
  INITIAL_PORT = 7789
  INITIAL_MINOR = 1
  DRBD_RAW_SUFFIX = 'raw'
  DRBD_META_SUFFIX = 'meta'
  DRBD_CONFIG_TEMPLATE = McVirt.TEMPLATE_DIR + '/drbd_resource.conf'

  def __init__(self, vm_object, disk_id=None, drbd_minor=None, drbd_port=None, config=None, registered=False):
    """Set member variables and run the base init method"""
    self.config = \
      {
        'drbd_minor': drbd_minor,
        'drbd_port': drbd_port,
        'sync_state': True
      }

    Base.__init__(self, vm_object=vm_object, disk_id=disk_id, config=config, registered=registered)

  def _getAvailableDrbdPort(self):
    """Obtains the next available DRBD port"""
    # Obtain list of currently used DRBD ports
    used_ports = NodeDRBD.getUsedDrbdPorts(self.vm_object.mcvirt_object)
    available_port = None

    # Determine a free port
    test_port = DRBD.INITIAL_PORT

    while (available_port is None):
      if (test_port in used_ports):
        test_port += 1
      else:
        available_port = test_port

    return available_port

  def _getAvailableDrbdMinor(self):
    """Obtains the next available DRBD minor"""
    # Obtain list of currently used DRBD minors
    used_minor_ids = NodeDRBD.getUsedDrbdMinors(self.vm_object.mcvirt_object)
    available_minor_id = None

    # Determine a free minor
    test_minor_id = DRBD.INITIAL_MINOR

    while (available_minor_id is None):
      if (test_minor_id in used_minor_ids):
        test_minor_id += 1
      else:
        available_minor_id = test_minor_id

    return available_minor_id

  def _getLogicalVolumeName(self, lv_type):
    """Returns the logical volume name for a given logical volume type"""
    return 'mcvirt_vm-%s-disk-%s-drbd-%s' % (self.vm_object.getName(), self.getId(), lv_type)

  def _getResourceName(self):
    """Returns the DRBD resource name for the hard drive object"""
    return 'mcvirt_vm-%s-disk-%s' % (self.vm_object.getName(), self.getId())

  def _getDrbdMinor(self):
    """Returns the DRBD port assigned to the hard drive"""
    if (self.config['drbd_minor'] is None):
      self.config['drbd_minor'] = self._getAvailableDrbdMinor()

    return self.config['drbd_minor']

  def _getDrbdPort(self):
    """Returns the DRBD port assigned to the hard drive"""
    if (self.config['drbd_port'] is None):
      self.config['drbd_port'] = self._getAvailableDrbdPort()

    return self.config['drbd_port']

  def _getDrbdDevice(self):
    """Returns the block object path for the DRBD volume"""
    return '/dev/drbd%s' % self._getDrbdMinor()

  def _getDiskPath(self):
    """Returns the path of the raw disk image"""
    return self._getDrbdDevice()

  def _generateDrbdConfig(self):
    """Generates the DRBD resource configuration"""
    from Cheetah.Template import Template

    # Create configuration for use with the template
    raw_lv_path = self._getLogicalVolumePath(self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX))
    meta_lv_path = self._getLogicalVolumePath(self._getLogicalVolumeName(self.DRBD_META_SUFFIX))
    drbd_config = \
    {
      'resource_name': self._getResourceName(),
      'block_device_path': self._getDrbdDevice(),
      'raw_lv_path': raw_lv_path,
      'meta_lv_path': meta_lv_path,
      'drbd_port': self._getDrbdPort(),
      'nodes': []
    }

    # Add local node to the DRBD config
    from mcvirt.cluster.cluster import Cluster
    cluster_object = Cluster(self.vm_object.mcvirt_object)
    node_template_conf = \
    {
      'name': Cluster.getHostname(),
      'ip_address': cluster_object.getClusterIpAddress()
    }
    drbd_config['nodes'].append(node_template_conf)

    # Add remote nodes to DRBD config
    for node in cluster_object.getNodes():
      node_config = cluster_object.getNodeConfig(node)
      node_template_conf = \
        {
          'name': node,
          'ip_address': node_config['ip_address']
        }
      drbd_config['nodes'].append(node_template_conf)

    # Replace the variables in the template with the local DRBD configuration
    config_content = Template(file=self.DRBD_CONFIG_TEMPLATE, searchList=[drbd_config])

    # Write the DRBD configuration
    fh = open(self._getDrbdConfigFile(), 'w')
    fh.write(config_content.respond())
    fh.close()

  def _removeDrbdConfig(self):
    """Remove the DRBD resource configuration from the node"""
    os.remove(self._getDrbdConfigFile())

  def _getDrbdConfigFile(self):
    """Returns the path of the DRBD resource configuration file"""
    return NodeDRBD.CONFIG_DIRECTORY + '/' + self._getResourceName() + '.res'

  def _calculateMetaDataSize(self):
    """Determines the size of the DRBD meta volume"""
    import math

    raw_logical_volume_name = self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)
    logical_volume_path = self._getLogicalVolumePath(raw_logical_volume_name)

    # Obtain size of raw volume
    _, raw_size_sectors, _ = System.runCommand(['blockdev', '--getsz', logical_volume_path])
    raw_size_sectors = int(raw_size_sectors.strip())

    # Obtain size of sectors
    _, sector_size, _ = System.runCommand(['blockdev', '--getss', logical_volume_path])
    sector_size = int(sector_size.strip())

    # Follow the DRBD meta data calculation formula, see
    # https://drbd.linbit.com/users-guide/ch-internals.html#s-external-meta-data
    meta_size_formula_step_1 = int(math.ceil(raw_size_sectors / 262144))
    meta_size_formula_step_2 = meta_size_formula_step_1 * 8
    meta_size_sectors = meta_size_formula_step_2 + 72

    # Convert meta size in sectors to Mebibytes
    meta_size_mebibytes = math.ceil((meta_size_sectors * sector_size) / (1024 ^ 2))

    # Convert from float to int and return
    return int(meta_size_mebibytes)

  def _getMcVirtConfig(self):
    """Returns the McVirt hard drive configuration for the DRBD hard drive"""
    mcvirt_config = \
    {
      'drbd_port': self.config['drbd_port'],
      'drbd_minor': self.config['drbd_minor'],
      'sync_state': self.config['sync_state']
    }
    return mcvirt_config

  def _getBackupLogicalVolume(self):
    """Returns the storage device for the backup"""
    return self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)

  def _getBackupSnapshotLogicalVolume(self):
    """Returns the logical volume name for the backup snapshot"""
    return self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX) + self.SNAPSHOT_SUFFIX

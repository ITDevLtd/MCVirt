#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.virtual_machine.hard_drive.config.base import Base

class Local(Base):
  """Provides a configuration interface for local hard drive objects"""

  MAXIMUM_DEVICES = 4

  def __init__(self, vm_object, disk_id=None, config=None, registered=False):
    """Create config has for storing variables and run the base init method"""
    self.config = {}
    super(Local, self).__init__(vm_object=vm_object, disk_id=disk_id, config=config, registered=registered)

  def _getDiskPath(self):
    """Returns the path of the raw disk image"""
    return self._getLogicalVolumePath(self._getDiskName())

  def _getDiskName(self):
    """Returns the name of a disk logical volume, for a given VM"""
    if (self):
      vm_name = self.vm_object.getName()
      disk_id = self.getId()
    return 'mcvirt_vm-%s-disk-%s' % (vm_name, disk_id)

  def _getMCVirtConfig(self):
    """Returns the MCVirt hard drive configuration for the Local hard drive"""
    # There are no configurations for the disk stored by MCVirt
    return {}

  def _getBackupLogicalVolume(self):
    """Returns the storage device for the backup"""
    return self._getDiskName()

  def _getBackupSnapshotLogicalVolume(self):
    """Returns the logical volume name for the backup snapshot"""
    return self._getDiskName + self.SNAPSHOT_SUFFIX

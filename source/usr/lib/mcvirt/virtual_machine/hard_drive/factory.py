#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.mcvirt import McVirtException
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import DRBD
from mcvirt.virtual_machine.hard_drive.base import Base

class UnkownStorageTypeException(McVirtException):
  """An hard drive object with an unknown disk type has been initialised"""
  pass

class Factory():
  """Provides a factory for creating hard drive objects"""

  @staticmethod
  def getObject(vm_object, disk_id):
    """Returns the storage object for a given disk"""
    vm_config = vm_object.getConfigObject().getConfig()
    storage_type = vm_config['hard_disks'][str(disk_id)]['type']

    return Factory.getClass(storage_type)(vm_object, disk_id)

  @staticmethod
  def create(vm_object, size, storage_type):
    """Performs the creation of a hard drive, using a given storage type"""
    return Factory.getClass(storage_type).create(vm_object, size)

  @staticmethod
  def getClass(storage_type):
    """Obtains the hard drive class for a given storage type"""
    for hard_drive_class in [DRBD, Local]:
      if (storage_type == hard_drive_class.TYPE):
        return hard_drive_class
    raise UnkownStorageTypeException('Attempted to initialise an unknown storage type: %s' % (storage_type))
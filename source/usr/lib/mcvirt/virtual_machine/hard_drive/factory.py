#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.mcvirt import McVirtException
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import DRBD
from mcvirt.virtual_machine.hard_drive.config.base import Base as ConfigBase
from mcvirt.virtual_machine.hard_drive.config.local import Local as ConfigLocal
from mcvirt.virtual_machine.hard_drive.config.drbd import DRBD as ConfigDRBD

class UnkownStorageTypeException(McVirtException):
  """An hard drive object with an unknown disk type has been initialised"""
  pass

class Factory():
  """Provides a factory for creating hard drive/hard drive config objects"""

  STORAGE_TYPES = [Local, DRBD]
  DEFAULT_STORAGE_TYPE = 'Local'

  @staticmethod
  def getObject(vm_object, disk_id):
    """Returns the storage object for a given disk"""
    vm_config = vm_object.getConfigObject().getConfig()
    storage_type = vm_config['storage_type']

    return Factory.getClass(storage_type)(vm_object, disk_id)

  @staticmethod
  def getConfigObject(vm_object, storage_type, disk_id=None, config=None):
    """Returns the config object for a given disk"""
    for config_class in [ConfigLocal, ConfigDRBD]:
      if (storage_type == config_class.__name__):
        return config_class(vm_object, disk_id, config=config)
    raise UnkownStorageTypeException('Attempted to initialise an unknown storage config type: %s' % storage_type)

  @staticmethod
  def getRemoteConfigObject(mcvirt_instance, arguments):
    """Returns a hard drive config object, using arguments sent to a remote machine"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
    return Factory.getConfigObject(vm_object=vm_object, storage_type=arguments['storage_type'], config=arguments['config'])

  @staticmethod
  def create(vm_object, size, storage_type):
    """Performs the creation of a hard drive, using a given storage type"""
    return Factory.getClass(storage_type).create(vm_object, size)

  @staticmethod
  def getStorageTypes():
    """Returns the available storage types that McVirt provides"""
    return Factory.STORAGE_TYPES

  @staticmethod
  def getClass(storage_type):
    """Obtains the hard drive class for a given storage type"""
    for hard_drive_class in Factory.getStorageTypes():
      if (storage_type == hard_drive_class.__name__):
        return hard_drive_class
    raise UnkownStorageTypeException('Attempted to initialise an unknown storage type: %s' % (storage_type))
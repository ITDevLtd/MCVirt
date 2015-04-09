#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.mcvirt_config import McVirtConfig
from mcvirt.mcvirt import McVirtException
import xml.etree.ElementTree as ET
import os
from mcvirt.system import System, McVirtCommandException

class HardDriveDoesNotExistException(McVirtException):
  """The given hard drive does not exist"""
  pass


class StorageTypesCannotBeMixedException(McVirtException):
  """Storage types cannot be mixed within a single VM"""
  pass


class LogicalVolumeDoesNotExistException(McVirtException):
  """A required logical volume does not exist"""
  pass


class Base(object):
  """Provides base operations to manage all hard drives, used by VMs"""

  def __init__(self, disk_id):
    """Sets member variables"""
    if (not self._checkExists()):
      raise HardDriveDoesNotExistException('Disk %s for %s does not exist' % (self.getConfigObject().getId(), self.getVmObject().name))

  def getConfigObject(self):
    """Returns the config object for the hard drive"""
    return self.config

  def getVmObject(self):
    """Returns the VM object that the hard drive is attached to"""
    return self.getConfigObject().vm_object

  def getType(self):
    """Returns the type of storage for the hard drive"""
    return self.__class__.__name__

  def delete(self):
    """Deletes the logical volume for the disk"""
    from mcvirt.virtual_machine.hard_drive.factory import Factory

    # Remove backing storage
    self._removeStorage()

    # If the VM that the hard drive is attached to is registered on the local
    # node, remove the hard drive from the LibVirt configuration
    if (self.getVmObject().isRegisteredLocally()):
      Factory.getClass(self.getType())._unregisterLibvirt(self.getConfigObject())

    # Remove the hard drive from the McVirt VM configuration
    Factory.getClass(self.getType())._removeFromVirtualMachine(self.getConfigObject())

  @staticmethod
  def _removeFromVirtualMachine(config_object):
    """Removes the hard drive configuration from the McVirt VM configuration"""
    # Update VM config file
    def removeDiskFromConfig(vm_config):
      del(vm_config['hard_disks'][str(config_object.getId())])

    config_object.vm_object.getConfigObject().updateConfig(removeDiskFromConfig)

  @staticmethod
  def _unregisterLibvirt(config_object):
    """Removes the hard drive from the LibVirt configuration for the VM"""
    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      device_xml = domain_xml.find('./devices')
      disk_xml = device_xml.find('./disk/target[@dev="%s"]/..' % config_object._getTargetDev())
      device_xml.remove(disk_xml)

    # Update libvirt configuration
    config_object.vm_object.editConfig(updateXML)

  @staticmethod
  def _addToVirtualMachine(config_object, activate=True):
    """Adds the current disk to a give VM"""
    from mcvirt.virtual_machine.hard_drive.factory import Factory

    # Update the libvirt domain XML configuration
    if (activate):
      Factory.getClass(config_object._getType())._registerLibvirt(config_object)

    # Update the VM storage config
    Factory.getClass(config_object._getType())._setVmStorageType(config_object)

    # Update VM config file
    def addDiskToConfig(vm_config):
      vm_config['hard_disks'][str(config_object.getId())] = config_object._getMcVirtConfig()

    config_object.vm_object.getConfigObject().updateConfig(addDiskToConfig)

  @staticmethod
  def _registerLibvirt(config_object):
    """Register the hard drive with the Libvirt VM configuration"""

    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      drive_xml = config_object._generateLibvirtXml()
      device_xml = domain_xml.find('./devices')
      device_xml.append(drive_xml)

    # Update libvirt configuration
    config_object.vm_object.editConfig(updateXML)

  @staticmethod
  def _setVmStorageType(config_object):
    """Set the VM configuration storage type to the current hard drive type"""
    # Ensure VM has not already been configured with disks that
    # do not match the type specified
    number_of_disks = len(config_object.vm_object.getDiskObjects())
    current_storage_type = config_object.vm_object.getConfigObject().getConfig()['storage_type']
    if (current_storage_type is not config_object._getType()):
      if (number_of_disks):
        raise StorageTypesCannotBeMixedException('The VM (%s) is already configured with %s disks' %
                                                 (config_object.vm_object.getName(), current_storage_type))

      def updateStorageTypeConfig(config):
        config['storage_type'] = config_object._getType()
      config_object.vm_object.getConfigObject().updateConfig(updateStorageTypeConfig)

  @staticmethod
  def _createLogicalVolume(config_object, name, size, perform_on_nodes=False):
    """Creates a logical volume on the node/cluster"""
    from mcvirt.cluster.cluster import Cluster
    volume_group = config_object._getVolumeGroup()

    # Create command list
    command_args = ['/sbin/lvcreate', volume_group, '--name', name, '--size', '%sM' % size]
    try:
      # Create on local node
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)

      if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
        cluster = Cluster(config_object.vm_object.mcvirt_object)

        # Run on remote nodes
        cluster.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                 {'config': config_object._dumpConfig(),
                                  'name': name,
                                  'size': size})

    except McVirtCommandException, e:
      # Remove any logical volumes that had been created if one of them fails
      Base._removeLogicalVolume(config_object, name, ignore_non_existent=True, perform_on_nodes=perform_on_nodes)
      raise McVirtException("Error whilst creating disk logical volume:\n" + str(e))

  @staticmethod
  def _removeLogicalVolume(config_object, name, ignore_non_existent=False, perform_on_nodes=False):
    """Removes a logical volume from the node/cluster"""
    from mcvirt.cluster.cluster import Cluster

    # Create command arguments
    command_args = ['lvremove', '-f', config_object._getLogicalVolumePath(name)]
    try:
      # Determine if logical volume exists before attempting to remove it
      if (not (ignore_non_existent and not Base._checkLogicalVolumeExists(config_object, name))):
        (exit_code, command_output, command_stderr) = System.runCommand(command_args)

      if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
        cluster = Cluster(config_object.vm_object.mcvirt_object)

        # Run on remote nodes
        cluster.runRemoteCommand('virtual_machine-hard_drive-removeLogicalVolume',
                                 {'config': config_object._dumpConfig(),
                                  'name': name})
    except McVirtCommandException, e:
      raise McVirtException("Error whilst removing disk logical volume:\n" + str(e))

  @staticmethod
  def _zeroLogicalVolume(config_object, name, size, perform_on_nodes=False):
    """Blanks a logical volume by filling it with null data"""
    from mcvirt.cluster.cluster import Cluster

    # Obtain the path of the logical volume
    lv_path = config_object._getLogicalVolumePath(name)

    # Create command arguments
    command_args = ['dd', 'if=/dev/zero', 'of=%s' % lv_path, 'bs=1M', 'count=%s' % size]
    try:
      # Create logical volume on local node
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)

      if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
        cluster = Cluster(config_object.vm_object.mcvirt_object)

        # Create logical volume on remote nodes
        cluster.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                 {'config': config_object._dumpConfig(),
                                  'name': name, 'size': size})
    except McVirtCommandException, e:
      raise McVirtException("Error whilst zeroing logical volume:\n" + str(e))

  @staticmethod
  def _ensureLogicalVolumeExists(config_object, name):
    """Ensures that a logical volume exists, throwing an exception if it does not"""
    if (not Base._checkLogicalVolumeExists(config_object, name)):
      from mcvirt.cluster.cluster import Cluster
      raise LogicalVolumeDoesNotExistException('Logical volume %s does not exist on %s' % (name, Cluster.getHostname()))

  @staticmethod
  def _checkLogicalVolumeExists(config_object, name):
    """Determines if a logical volume exists, returning 1 if present and 0 if not"""
    return os.path.lexists(config_object._getLogicalVolumePath(name))

  @staticmethod
  def _activateLogicalVolume(config_object, name, perform_on_nodes=False):
    """Activates a logical volume on the node/cluster"""
    from mcvirt.cluster.cluster import Cluster

    # Obtain logical volume path
    lv_path = config_object._getLogicalVolumePath(name)

    # Create command arguments
    command_args = ['lvchange', '-a', 'y', lv_path]
    try:
      # Run on the local node
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)

      if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
        cluster = Cluster(config_object.vm_object.mcvirt_object)

        # Run on remote nodes
        cluster.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                 {'config': config_object._dumpConfig(),
                                  'name': name})
    except McVirtCommandException, e:
      raise McVirtException("Error whilst zeroing logical volume:\n" + str(e))

  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    raise NotImplementedError

  def _checkExists(self):
    """Checks if the disk exists"""
    raise NotImplementedError

  def clone(self, destination_vm_object):
    """Clone a VM, using snapshotting, attaching it to the new VM object"""
    raise NotImplementedError

  @staticmethod
  def create(vm_object, size):
    """Creates a new disk image, attaches the disk to the VM and records the disk
    in the VM configuration"""
    raise NotImplementedError

  def activateDisk(self):
    """Activates the storage volume"""
    raise NotImplementedError

  def getSize(self):
    """Gets the size of the disk (in MB)"""
    raise NotImplementedError
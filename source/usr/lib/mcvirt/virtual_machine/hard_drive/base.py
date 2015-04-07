#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.mcvirt_config import McVirtConfig
from mcvirt.mcvirt import McVirtException
import xml.etree.ElementTree as ET
from mcvirt.system import System

class HardDriveDoesNotExistException(McVirtException):
  """The given hard drive does not exist"""
  pass

class ReachedMaximumStorageDevicesException(McVirtException):
  """Reached the limit to number of hard disks attached to VM"""
  pass

class Base(object):

  def __init__(self, vm_object, disk_id):
    """Sets member variables"""
    self.vm_object = vm_object
    self.host_volume_group = McVirtConfig().getConfig()['vm_storage_vg']
    self.id = disk_id
    if (not self._checkExists()):
      raise HardDriveDoesNotExistException('Disk %s for %s does not exist' % (self.getId(), self.vm_object.name))

  def getType(self):
    """Returns the type of storage for the hard drive"""
    return self.TYPE

  def getDiskConfig(self):
    """Returns the disk configuration for the hard drive"""
    vm_config = self.vm_object.getConfigObject().getConfig()
    return vm_config['hard_disks'][self.getId()]

  def getId(self):
    """Returns the disk ID of the current disk"""
    return self.id

  def _getTargetDev(self):
    """Determines the target dev, based on the disk's ID"""
    # Check that the id is less than 4, as a VM can only have a maximum of 4 disks
    if (int(self.getId()) > self.MAXIMUM_DEVICES):
      raise ReachedMaximumStorageDevicesException('A maximum of (%s) hard drives can be mapped to a VM' % self.MAXIMUM_DEVICES)

    # Use ascii numbers to map 1 => a, 2 => b, etc...
    return 'sd' + chr(96 + int(self.getId()))

  @staticmethod
  def _getAvailableId(vm_object):
    """Obtains the next available ID for the VM hard drive, by scanning the IDs
    of disks attached to the VM"""
    found_available_id = False
    disk_id = 0
    vm_config = vm_object.getConfigObject().getConfig()
    disks = vm_config['hard_disks']
    while (not found_available_id):
      disk_id += 1
      if (not disk_id in disks):
        found_available_id = True
    return disk_id

  def delete(self):
    """Delete the logical volume for the disk"""
    # Remove backing storage
    self._removeStorage()

    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      device_xml = domain_xml.find('./devices')
      disk_xml = device_xml.find('./disk/target[@dev="%s"]/..' % self._getTargetDev())
      device_xml.remove(disk_xml)

    # Update libvirt configuration
    self.vm_object.editConfig(updateXML)

    # Update VM config file
    def removeDiskFromConfig(vm_config):
      del(vm_config['hard_disks'][self.getId()])

    self.vm_object.getConfigObject().updateConfig(removeDiskFromConfig)

  def _addToVirtualMachine(self):
    """Adds the current disk to a give VM"""
    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      drive_xml = self.createXML()
      device_xml = domain_xml.find('./devices')
      device_xml.append(drive_xml)

    try:
      # Update libvirt configuration
      self.vm_object.editConfig(updateXML)

      # Update VM config file
      def addDiskToConfig(vm_config):
        vm_config['hard_disks'][self.getId()] = \
          {
            'type': self.getType()
          }

      self.vm_object.getConfigObject().updateConfig(addDiskToConfig)
    except Exception, e:
      # If attaching the HDD to the VM fails, remove the disk image
      self._removeStorage()
      raise McVirtException('An error occurred whilst attaching the disk to the VM' + str(e))

  def createXML(self):
    """Creates a basic libvirt XML configuration for the connection to the disk"""
    # Create the base disk XML element
    device_xml = ET.Element('disk')
    device_xml.set('type', 'block')
    device_xml.set('device', 'disk')

    # Configure the interface driver to the disk
    driver_xml = ET.SubElement(device_xml, 'driver')
    driver_xml.set('name', 'qemu')
    driver_xml.set('type', 'raw')
    driver_xml.set('cache', 'none')

    # Configure the source of the disk
    source_xml = ET.SubElement(device_xml, 'source')
    source_xml.set('dev', self._getDiskPath())

    # Configure the target
    target_xml = ET.SubElement(device_xml, 'target')
    target_xml.set('dev', '%s' % self._getTargetDev())
    target_xml.set('bus', 'virtio')

    return device_xml

  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    raise NotImplementedError

  def _checkExists(self):
    """Checks if the disk exists"""
    raise NotImplementedError

  def _getDiskPath(self):
    """Returns the path of the raw disk image"""
    raise NotImplementedError

  def getSize(self):
    """Gets the size of the disk (in MB)"""
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

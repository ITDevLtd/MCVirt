#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET
import commands
import os

from mcvirt.mcvirt import McVirtException

class HardDrive:
  """Provides operations to manage hard drives, used by VMs"""

  def __init__(self, vm_object, id):
    """Sets member variables and obtains libvirt domain object"""

    self.vm_object = vm_object
    self.id = id
    if (not self.__checkExists()):
      raise McVirtException('Disk %s for %s does not exist' % (self.id, self.vm_object.name))


  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    # Ensure VM is stopped
    if (self.vm_object.isRunning()):
      raise McVirtException('VM must be stopped before increasing disk size')
    disk_path = HardDrive.getDiskPath(self.vm_object.name, self.id)
    command = 'dd if=/dev/zero bs=1M count=%s >> %s' % (increase_size, disk_path)
    (status, output) = commands.getstatusoutput(command)
    if (status):
      raise McVirtException("Error whilst creating disk image:\nCommand: %s\nExit code: %s\nOutput: %s" % (command, status, output))


  def __checkExists(self):
    """Checks if a disk exists, which is required before any operations
    can be performed on the disk"""
    if (os.path.isfile(HardDrive.getDiskPath(self.vm_object.name, self.id))):
      return True
    else:
      return False


  @staticmethod
  def getDiskPath(name, disk_number = 1):
    """Returns the path of a disk image for a given VM"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine

    return VirtualMachine.getVMDir(name) + '/' + 'vm-%s-disk-%s.raw' % (name, disk_number)


  @staticmethod
  def create(vm_object, size):
    """Creates a new disk image, attaches the disk to the VM and records the disk
    in the VM configuration"""
    disk_id = HardDrive.__getAvailableId(vm_object)
    disk_path = HardDrive.getDiskPath(vm_object.name, disk_id)

    # Ensure the disk doesn't already exist
    if (os.path.isfile(disk_path)):
      raise McVirtException('Disk already exists: %s' % disk_path)

    # Create the raw disk image
    command = 'dd if=/dev/zero of=%s bs=1M count=%s' % (disk_path, size)
    (status, output) = commands.getstatusoutput(command)
    if (status):
      raise McVirtException("Error whilst creating disk image:\nCommand: %s\nExit code: %s\nOutput: %s" % (command, status, output))

    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      drive_xml = HardDrive.createXML(disk_path, disk_id)
      device_xml = domain_xml.find('./devices')
      device_xml.append(drive_xml)
      print 'Added disk'

    try:
      # Update libvirt configuration
      vm_object.editConfig(updateXML)

      # Update VM config file
      vm_config = vm_object.config.getConfig()
      vm_config['disks'].append(disk_id)
      vm_object.config.updateConfig(vm_config)
    except:
      # If attaching the HDD to the VM fails, remove the disk image
      os.unlink(disk_path)
      raise McVirtException('An error occured whilst attaching the disk to the VM')


  @staticmethod
  def __getAvailableId(vm_object):
    """Obtains the next available ID for the VM hard drive, by scanning the IDs
    of disks attached to the VM"""
    found_available_id = False
    disk_id = 0
    vm_config = vm_object.config.getConfig()
    disks = vm_config['disks']
    while (not found_available_id):
      disk_id += 1
      if (not disk_id in disks):
        found_available_id = True
    return disk_id


  @staticmethod
  def getTargetDev(disk_id):
    """Determines the target dev, based on the disk's ID"""
    # Check that the id is less than 4, as a VM can only have a maximum of 4 disks
    if (disk_id > 4):
      raise McVirtException('A maximum of 4 hard drives can be mapped to a VM')

    # Use ascii numbers to map 1 => a, 2 => b, etc...
    return chr(96 + int(disk_id))


  @staticmethod
  def createXML(path, disk_id):
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
    source_xml.set('dev', path)

    # Configure the target
    target_xml = ET.SubElement(device_xml, 'target')
    target_xml.set('dev', 'sd%s' % HardDrive.getTargetDev(disk_id))
    target_xml.set('bus', 'virtio')

    return device_xml
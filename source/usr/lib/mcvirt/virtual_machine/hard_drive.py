#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET
import subprocess
import os

from mcvirt.system import System
from mcvirt.mcvirt import McVirt, McVirtException, McVirtCommandException
from mcvirt.mcvirt_config import McVirtConfig

class HardDrive:
  """Provides operations to manage hard drives, used by VMs"""

  def __init__(self, vm_object, id):
    """Sets member variables and obtains libvirt domain object"""
    self.vm_object = vm_object
    self.host_volume_group = McVirtConfig().getConfig()['vm_storage_vg']
    self.id = id
    self.path = HardDrive.getDiskPath(self.host_volume_group, self.vm_object.name, self.id)
    if (not self._checkExists()):
      raise McVirtException('Disk %s for %s does not exist' % (self.id, self.vm_object.name))

  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    # Ensure VM is stopped
    if (self.vm_object.isRunning()):
      raise McVirtException('VM must be stopped before increasing disk size')

    # Ensure that VM has not been cloned and is not a clone
    if (self.vm_object.getCloneParent() or self.vm_object.getCloneChildren()):
      raise McVirtException('Cannot increase the disk of a cloned VM or a clone.')

    command_args = ('lvextend', '-L', '+%sM' % increase_size, self.path)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst extending logical volume:\n" + str(e))

  def _checkExists(self):
    """Checks if a disk exists, which is required before any operations
    can be performed on the disk"""
    if (os.path.lexists(self.path)):
      return True
    else:
      return False

  @staticmethod
  def getDiskPath(volume_group, vm_name, disk_number = 1):
    """Returns the path of a disk image for a given VM"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine

    return '/dev/' + volume_group + '/' + HardDrive.getDiskName(vm_name, disk_number)

  @staticmethod
  def getDiskName(vm_name, disk_number = 1):
    """Returns the name of a disk logical volume, for a given VM"""
    return 'mcvirt_vm-%s-disk-%s' % (vm_name, disk_number)

  def delete(self):
    """Delete the logical volume for the disk"""
    target_dev = HardDrive.getTargetDev(self.id)
    vm_object = self.vm_object

    # Remove logical volume
    HardDrive._removeLogicalVolume(self.path)

    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      device_xml = domain_xml.find('./devices')
      disk_xml = device_xml.find('./disk/target[@dev="%s"]/..' % target_dev)
      device_xml.remove(disk_xml)

    # Update libvirt configuration
    vm_object.editConfig(updateXML)

    # Update VM config file
    def removeDiskFromConfig(vm_config):
      vm_config['disks'].remove(self.id)

    vm_object.getConfigObject().updateConfig(removeDiskFromConfig)

  @staticmethod
  def _removeLogicalVolume(path):
    """Removes a logical volume"""
    command_args = ('lvremove', '-f', path)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst removing disk logical volume:\n" + str(e))

  def getSize(self):
    """Gets the size of the disk (in MB)"""
    # Use 'lvs' to obtain the size of the disk
    command_args = ('lvs', '--nosuffix', '--noheadings', '--units', 'm', '--options', 'lv_size', self.path)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst obtaining the size of the logical volume:\n" + str(e))

    lv_size = command_output.strip().split('.')[0]
    return int(lv_size)

  def getId(self):
    """Returns the disk ID of the current disk"""
    return self.id

  def clone(self, destination_vm_object):
    """Clone a VM, using snapshotting, attaching it to the new VM object"""
    new_logical_volume_name = HardDrive.getDiskName(destination_vm_object.getName(), self.id)
    disk_size = self.getSize()

    # Perform a logical volume snapshot
    command_args = ('lvcreate', '-L', '%sM' % disk_size, '-s', '-n', new_logical_volume_name, self.path)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst cloning disk logical volume:\n" + str(e))

    new_disk_object = HardDrive(destination_vm_object, self.id)
    new_disk_object._addToVirtualMachine()

  @staticmethod
  def create(vm_object, size):
    """Creates a new disk image, attaches the disk to the VM and records the disk
    in the VM configuration"""
    disk_id = HardDrive._getAvailableId(vm_object)
    volume_group = McVirtConfig().getConfig()['vm_storage_vg']
    disk_path = HardDrive.getDiskPath(volume_group, vm_object.name, disk_id)
    logical_volume_name = HardDrive.getDiskName(vm_object.name, disk_id)

    # Ensure the disk doesn't already exist
    if (os.path.lexists(disk_path)):
      raise McVirtException('Disk already exists: %s' % disk_path)

    # Create the raw disk image
    command_args = ('lvcreate', volume_group, '--name', logical_volume_name, '--size', '%sM' % size)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst creating disk logical volume:\n" + str(e))

    disk_object = HardDrive(vm_object, disk_id)
    disk_object._addToVirtualMachine()

  def _addToVirtualMachine(self):
    """Adds the current disk to a give VM"""
    disk_id = self.id
    volume_group = self.host_volume_group
    disk_path = self.path
    vm_object = self.vm_object

    # Update the libvirt domain XML configuration
    def updateXML(domain_xml):
      from mcvirt.virtual_machine.virtual_machine import VirtualMachine
      drive_xml = HardDrive.createXML(disk_path, disk_id)
      device_xml = domain_xml.find('./devices')
      device_xml.append(drive_xml)

    try:
      # Update libvirt configuration
      vm_object.editConfig(updateXML)

      # Update VM config file
      def addDiskToConfig(vm_config):
        vm_config['disks'].append(disk_id)

      vm_object.getConfigObject().updateConfig(addDiskToConfig)
    except:
      # If attaching the HDD to the VM fails, remove the disk image
      HardDrive._removeLogicalVolume(disk_path)
      raise McVirtException('An error occured whilst attaching the disk to the VM')

  def activateDisk(self):
    """Starts the disk logical volume"""
    command_args = ('lvchange', '-a', 'y', self.path)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst activating disk logical volume:\n" + str(e))

  @staticmethod
  def _getAvailableId(vm_object):
    """Obtains the next available ID for the VM hard drive, by scanning the IDs
    of disks attached to the VM"""
    found_available_id = False
    disk_id = 0
    vm_config = vm_object.getConfigObject().getConfig()
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
    return 'sd' + chr(96 + int(disk_id))

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
    target_xml.set('dev', '%s' % HardDrive.getTargetDev(disk_id))
    target_xml.set('bus', 'virtio')

    return device_xml
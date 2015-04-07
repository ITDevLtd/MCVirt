#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import subprocess
import os

from mcvirt.system import System, McVirtCommandException
from mcvirt.mcvirt import McVirt, McVirtException
from mcvirt.mcvirt_config import McVirtConfig
from base import Base

class Local(Base):
  """Provides operations to manage hard drives, used by VMs"""

  MAXIMUM_DEVICES = 4
  TYPE = 2

  def __init__(self, vm_object, disk_id):
    """Sets member variables and obtains libvirt domain object"""
    super(Local, self).__init__(vm_object, disk_id)

  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    # Ensure VM is stopped
    if (self.vm_object.getState()):
      raise McVirtException('VM must be stopped before increasing disk size')

    # Ensure that VM has not been cloned and is not a clone
    if (self.vm_object.getCloneParent() or self.vm_object.getCloneChildren()):
      raise McVirtException('Cannot increase the disk of a cloned VM or a clone.')

    command_args = ('lvextend', '-L', '+%sM' % increase_size, self._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst extending logical volume:\n" + str(e))

  def _checkExists(self):
    """Checks if a disk exists, which is required before any operations
    can be performed on the disk"""
    if (os.path.lexists(self._getDiskPath())):
      return True
    else:
      return False

  def _getDiskPath(self):
    """Returns the path of the raw disk image for the given disk object"""
    volume_group = McVirtConfig().getConfig()['vm_storage_vg']
    return Local.getDiskPath(volume_group, self.vm_object.getName(), self.getId())

  @staticmethod
  def getDiskPath(volume_group, vm_name, disk_number):
    """Returns the path of the raw disk image"""
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine

    return '/dev/' + volume_group + '/' + Local.getDiskName(vm_name, disk_number)

  @staticmethod
  def getDiskName(vm_name, disk_number):
    """Returns the name of a disk logical volume, for a given VM"""
    return 'mcvirt_vm-%s-disk-%s' % (vm_name, disk_number)

  def _removeStorage(self):
    """Removes a logical volume"""
    command_args = ('lvremove', '-f', self._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst removing disk logical volume:\n" + str(e))

  def getSize(self):
    """Gets the size of the disk (in MB)"""
    # Use 'lvs' to obtain the size of the disk
    command_args = ('lvs', '--nosuffix', '--noheadings', '--units', 'm', '--options', 'lv_size', self._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst obtaining the size of the logical volume:\n" + str(e))

    lv_size = command_output.strip().split('.')[0]
    return int(lv_size)

  def clone(self, destination_vm_object):
    """Clone a VM, using snapshotting, attaching it to the new VM object"""
    new_logical_volume_name = Local.getDiskName(destination_vm_object.getName(), self.id)
    disk_size = self.getSize()

    # Perform a logical volume snapshot
    command_args = ('lvcreate', '-L', '%sM' % disk_size, '-s', '-n', new_logical_volume_name, self._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst cloning disk logical volume:\n" + str(e))

    new_disk_object = Local(destination_vm_object, self.id)
    new_disk_object._addToVirtualMachine()

  @staticmethod
  def create(vm_object, size):
    """Creates a new disk image, attaches the disk to the VM and records the disk
    in the VM configuration"""
    disk_id = Local._getAvailableId(vm_object)
    volume_group = McVirtConfig().getConfig()['vm_storage_vg']
    disk_path = Local.getDiskPath(volume_group, vm_object.name, disk_id)
    logical_volume_name = Local.getDiskName(vm_object.name, disk_id)

    # Ensure the disk doesn't already exist
    if (os.path.lexists(disk_path)):
      raise McVirtException('Disk already exists: %s' % disk_path)

    # Create the raw disk image
    command_args = ('lvcreate', volume_group, '--name', logical_volume_name, '--size', '%sM' % size)
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst creating disk logical volume:\n" + str(e))

    disk_object = Local(vm_object, disk_id)
    disk_object._addToVirtualMachine()

  def activateDisk(self):
    """Starts the disk logical volume"""
    command_args = ('lvchange', '-a', 'y', self.getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst activating disk logical volume:\n" + str(e))

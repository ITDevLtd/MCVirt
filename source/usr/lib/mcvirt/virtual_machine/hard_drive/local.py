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
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.local import Local as ConfigLocal

class Local(Base):
  """Provides operations to manage local hard drives, used by VMs"""

  def __init__(self, vm_object, disk_id):
    """Sets member variables and obtains libvirt domain object"""
    self.config = ConfigLocal(vm_object=vm_object, disk_id=disk_id, registered=True)
    super(Local, self).__init__(disk_id=disk_id)

  def increaseSize(self, increase_size):
    """Increases the size of a VM hard drive, given the size to increase the drive by"""
    # Ensure VM is stopped
    if (self.getVmObject().getState()):
      raise McVirtException('VM must be stopped before increasing disk size')

    # Ensure that VM has not been cloned and is not a clone
    if (self.getVmObject().getCloneParent() or self.getVmObject().getCloneChildren()):
      raise McVirtException('Cannot increase the disk of a cloned VM or a clone.')

    command_args = ('lvextend', '-L', '+%sM' % increase_size, self.getConfigObject()._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst extending logical volume:\n" + str(e))

  def _checkExists(self):
    """Checks if a disk exists, which is required before any operations
    can be performed on the disk"""
    Local._ensureLogicalVolumeExists(self.getConfigObject(), self.getConfigObject()._getDiskName())
    return True

  def _removeStorage(self):
    """Removes the backing logical volume"""
    Local._removeLogicalVolume(self.getConfigObject(), self.getConfigObject()._getDiskName())

  def getSize(self):
    """Gets the size of the disk (in MB)"""
    return Local._getLogicalVolumeSize(self.getConfigObject(), self.getConfigObject()._getDiskName())

  def clone(self, destination_vm_object):
    """Clone a VM, using snapshotting, attaching it to the new VM object"""
    new_disk_config = ConfigLocal(vm_object=destination_vm_object, disk_id=self.getConfigObject().getId())
    new_logical_volume_name = new_disk_config._getDiskName()
    disk_size = self.getSize()

    # Perform a logical volume snapshot
    command_args = ('lvcreate', '-L', '%sM' % disk_size, '-s', '-n', new_logical_volume_name, self.getConfigObject()._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst cloning disk logical volume:\n" + str(e))

    new_disk_object = Local(destination_vm_object, self.getConfigObject().getId())
    new_disk_object._addToVirtualMachine()

  @staticmethod
  def create(vm_object, size):
    """Creates a new disk image, attaches the disk to the VM and records the disk
    in the VM configuration"""
    disk_config_object = ConfigLocal(vm_object=vm_object)
    disk_path = disk_config_object._getDiskPath()
    logical_volume_name = disk_config_object._getDiskName()

    # Ensure the disk doesn't already exist
    if (os.path.lexists(disk_path)):
      raise McVirtException('Disk already exists: %s' % disk_path)

    # Create the raw disk image
    Local._createLogicalVolume(disk_config_object, logical_volume_name, size)

    # Attach to VM and create disk object
    Local._addToVirtualMachine(disk_config_object)
    disk_object = Local(vm_object, disk_config_object.getId())
    return disk_object

  def activateDisk(self):
    """Starts the disk logical volume"""
    command_args = ('lvchange', '-a', 'y', self.getConfigObject()._getDiskPath())
    try:
      (exit_code, command_output, command_stderr) = System.runCommand(command_args)
    except McVirtCommandException, e:
      raise McVirtException("Error whilst activating disk logical volume:\n" + str(e))

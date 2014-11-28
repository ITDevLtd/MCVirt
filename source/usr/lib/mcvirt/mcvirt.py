#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys
import os
from lockfile import FileLock
import subprocess
from texttable import Texttable

from mcvirt_config import McVirtConfig
from auth import Auth

class McVirt:
  """Provides general McVirt functions"""

  TEMPLATE_DIR = '/usr/lib/mcvirt/templates'
  BASE_STORAGE_DIR = '/var/lib/mcvirt'
  BASE_VM_STORAGE_DIR = BASE_STORAGE_DIR + '/vm'
  ISO_STORAGE_DIR = BASE_STORAGE_DIR + '/iso'
  LOCK_FILE_DIR = '/var/run/lock/mcvirt'
  LOCK_FILE = LOCK_FILE_DIR + '/lock'

  def __init__(self, uri = None):
    """Checks lock file and performs initial connection to libvirt"""
    self.obtained_filelock = False
    self.config = McVirtConfig()
    self.auth = Auth(self.getConfigObject())

    # Create lock file, if it does not exist
    if (not os.path.isfile(self.LOCK_FILE)):
      if (not os.path.isdir(self.LOCK_FILE_DIR)):
        os.mkdir(self.LOCK_FILE_DIR)
      open(self.LOCK_FILE, 'a').close()

    # Attempt to lock lockfile
    self.lockfile_object = FileLock(self.LOCK_FILE)
    try:
      self.lockfile_object.acquire()
      self.obtained_filelock = True
    except:
      raise McVirtException('An instance of McVirt is already running')

    self._connect(uri)

  def __del__(self):
    """Removes McVirt lock file on object destruction"""
    if (self.obtained_filelock and self.lockfile_object.is_locked()):
      self.lockfile_object.release()

  def _connect(self, uri):
    """
    Connect to libvirt and store the connection as an object variable.
    Exit if an error occurs whilst connecting.
    """
    connection = libvirt.open(uri)
    if (connection == None):
      raise McVirtException('Failed to open connection to the hypervisor')
    else:
      self.connection = connection

  def getLibvirtConnection(self):
    """Obtains a connection to libvirt"""
    return self.connection

  def getConfigObject(self):
    """Obtains the instance of McVirt permissions"""
    return self.config

  def getAuthObject(self):
    """Returns an instance of the auth class"""
    return self.auth

  def getAllVirtualMachineObjects(self):
    """Obtain array of all domains from libvirt"""
    from virtual_machine.virtual_machine import VirtualMachine
    all_domains = self.getLibvirtConnection().listAllDomains()
    vm_objects = []
    for domain in all_domains:
      vm_objects.append(VirtualMachine(self, domain.name()))

    return vm_objects

  def listVms(self):
    """Lists the VMs that are currently on the host"""
    table = Texttable()
    table.set_deco(Texttable.HEADER | Texttable.VLINES)
    table.header(('VM Name', 'State'))

    for vm_object in self.getAllVirtualMachineObjects():
      table.add_row((vm_object.getName(), 'Running' if (vm_object.isRunning()) else 'Stopped'))
    print table.draw()

  @staticmethod
  def runCommand(command_args):
    """Runs system command, throwing an exception if the exit code is not 0"""
    command_process = subprocess.Popen(command_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if (command_process.wait()):
      raise McVirtCommandException("Command: %s\nExit code: %s\nOutput:\n%s" %
        (' '.join(command_args), command_process.returncode, command_process.stdout.read() + command_process.stderr.read()))
    return (command_process.returncode, command_process.stdout.read(), command_process.stderr.read())


class McVirtException(Exception):
  """Provides an exception to be thrown for errors in McVirt"""
  pass


class McVirtCommandException(McVirtException):
  """Provides an exception to be thrown after errors whilst calling external commands"""
  pass

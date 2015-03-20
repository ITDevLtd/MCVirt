#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys
import os
from lockfile import FileLock
from texttable import Texttable

class McVirt:
  """Provides general McVirt functions"""

  TEMPLATE_DIR = '/usr/lib/mcvirt/templates'
  BASE_STORAGE_DIR = '/var/lib/mcvirt'
  BASE_VM_STORAGE_DIR = BASE_STORAGE_DIR + '/vm'
  ISO_STORAGE_DIR = BASE_STORAGE_DIR + '/iso'
  LOCK_FILE_DIR = '/var/run/lock/mcvirt'
  LOCK_FILE = LOCK_FILE_DIR + '/lock'

  def __init__(self, uri = None, initialise_nodes=True, username=None):
    """Checks lock file and performs initial connection to libvirt"""
    # Configure custom username - used for unittests
    self.username = username

    # Create lock file, if it does not exist
    if (not os.path.isfile(self.LOCK_FILE)):
      if (not os.path.isdir(self.LOCK_FILE_DIR)):
        os.mkdir(self.LOCK_FILE_DIR)
      open(self.LOCK_FILE, 'a').close()

    # Attempt to lock lockfile
    self.lockfile_object = FileLock(self.LOCK_FILE)
    self.obtained_filelock = False
    try:
      self.lockfile_object.acquire(timeout=1)
      self.obtained_filelock = True
    except:
      raise McVirtException('An instance of McVirt is already running')

    # Create cluster instance, which will initialise the nodes
    from cluster.cluster import Cluster
    # Cluster configuration
    self.initialise_nodes = initialise_nodes
    self.remote_nodes = {}
    Cluster(self)

    # Connect to LibVirt
    self._connect(uri)

  def __del__(self):
    """Removes McVirt lock file on object destruction"""
    # Disconnect from each of the nodes
    for connection in self.remote_nodes:
      self.remote_nodes[connection] = None

    # Remove lock file
    if (self.obtained_filelock):
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

  def initialiseNodes(self):
    """Returns the status of the McVirt 'initialise_nodes' flag"""
    return self.initialise_nodes

  def getLibvirtConnection(self):
    """Obtains a connection to libvirt"""
    return self.connection

  def getAuthObject(self):
    from auth import Auth
    return Auth(self.username)

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


class McVirtException(Exception):
  """Provides an exception to be thrown for errors in McVirt"""
  pass


class McVirtCommandException(McVirtException):
  """Provides an exception to be thrown after errors whilst calling external commands"""
  pass

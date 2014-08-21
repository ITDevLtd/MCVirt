#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys
import os
from lockfile import FileLock

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
    if (self.obtained_filelock):
      self.lockfile_object.release()


  def _connect(self, uri):
    """
    Connect to libvirt and store the connection as an object variable.
    Exit if an error occures whilst connecting.
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
    return self.auth

class McVirtException(Exception):
  """Provides an exception to be throw for errors in McVirt"""

  def __init__(self, message):
    """Print the error message with the exception and exit"""
    print message
    sys.exit(1)
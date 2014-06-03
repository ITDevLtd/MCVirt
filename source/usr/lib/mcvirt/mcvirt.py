#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys

class McVirt:
  """Provides general McVirt functions"""

  TEMPLATE_DIR = '/usr/lib/mcvirt/templates'
  BASE_STORAGE_DIR = '/var/lib/mcvirt'
  BASE_VM_STORAGE_DIR = BASE_STORAGE_DIR + '/vm'
  ISO_STORAGE_DIR = BASE_STORAGE_DIR + '/iso'

  def __init__(self, uri = None):
    """Perform initial connection to libvirt"""

    self.__connect(uri)

  def __connect(self, uri):
    """
    Connect to libvirt and store the connection as an object variable.
    Exit if an error occures whilst connecting.
    """
    connection = libvirt.open(uri)
    if (connection == None):
      raise McVirtException('Failed to open connection to the hypervisor')
    else:
      self.connection = connection


class McVirtException(Exception):
  """Provides an exception to be throw for errors in McVirt"""

  def __init__(self, message):
    """Print the error message with the exception and exit"""
    print message
    sys.exit(1)
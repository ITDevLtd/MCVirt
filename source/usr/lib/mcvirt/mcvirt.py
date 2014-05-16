#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt

class McVirt:
  """Provides general McVirt functions"""

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
      print 'Failed to open connection to the hypervisor'
      sys.exit(1)
    else:
      self.connection = connection
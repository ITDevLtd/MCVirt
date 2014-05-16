#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys

class VirtualMachine:
  """Provides operations to manage a libvirt virtual machine"""

  def __init__(self, libvirt_connection, name):
    """Sets member variables and obtains libvirt domain object"""
    self.connection = libvirt_connection
    self.name = name

    # Ensure that the connection is alive
    if (not self.connection.isAlive()):
      print 'Connection not alive'
      sys.exit(1)

    # Create a libvirt domain object
    self.domain_object = self.__getDomainObject()


  def __getDomainObject(self):
    """Looks up libvirt domain object, based on VM name,
    and return object"""
    # Get the domain object.
    # An exception will be thrown if no domain
    # exists with the given name
    try:
      return self.connection.lookupByName(self.name)
    except:
      print 'The specified VM was not found: %s' % self.name
      sys.exit(1)


  def stop(self):
    """Stops the VM"""

    # Determine if VM is running
    if (self.domain_object.state()[0] == libvirt.VIR_DOMAIN_RUNNING):

      # Stop the VM
      self.domain_object.destroy()
      print 'Successfully stopped VM'

    # Otherwise, display an error
    else:
      print 'The VM is already shutdown'
      sys.exit(1)


  def start(self):
    """Starts the VM"""

    # Determine if VM is stopped
    if (self.domain_object.state()[0] != libvirt.VIR_DOMAIN_RUNNING):

      # Start the VM
      self.domain_object.create()
      print 'Successfully started VM'

    # Otherwise, display an error
    else:
      print 'The VM is already running'
      sys.exit(1)
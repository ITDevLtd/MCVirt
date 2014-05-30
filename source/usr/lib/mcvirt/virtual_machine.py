#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET
import re
from subprocess import call
import os
import shutil

from mcvirt import McVirt, McVirtException

class VirtualMachine:
  """Provides operations to manage a libvirt virtual machine"""

  def __init__(self, libvirt_connection, name):
    """Sets member variables and obtains libvirt domain object"""
    self.connection = libvirt_connection
    self.name = name

    # Ensure that the connection is alive
    if (not self.connection.isAlive()):
      raise McVirtException('Error: Connection not alive')

    # Check that the domain exists
    if (not VirtualMachine.__checkExists(self.connection, self.name)):
      raise McVirtException('Error: Virtual Machine does not exist')

    # Create a libvirt domain object
    self.domain_object = self.__getDomainObject()


  def __getDomainObject(self):
    """Looks up libvirt domain object, based on VM name,
    and return object"""
    # Get the domain object.
    return self.connection.lookupByName(self.name)


  def stop(self):
    """Stops the VM"""

    # Determine if VM is running
    if (self.domain_object.state()[0] == libvirt.VIR_DOMAIN_RUNNING):

      # Stop the VM
      self.domain_object.destroy()
      print 'Successfully stopped VM'

    else:
      raise McVirtException('The VM is already shutdown')


  def start(self):
    """Starts the VM"""

    # Determine if VM is stopped
    if (self.domain_object.state()[0] != libvirt.VIR_DOMAIN_RUNNING):

      # Start the VM
      self.domain_object.create()
      print 'Successfully started VM'

    else:
      raise McVirtException('The VM is already running')


  def delete(self, delete_disk = False):
    """Delete the VM - removing it from libvirt and from the filesystem"""

    # Determine if VM is running
    if (self.domain_object.state()[0] == libvirt.VIR_DOMAIN_RUNNING):
      raise McVirtException('Error: Can\'t delete running VM')

    # Undefine object from libvirt
    try:
      self.domain_object.undefine()
    except:
      raise McVirtException('Failed to delete VM from libvirt')
    print 'Successfully unregistered VM'

    # If 'delete_disk' has been passed as True, delete directory
    # from VM storage
    if (delete_disk):
      shutil.rmtree(VirtualMachine.getVMDir(self.name))
      print 'Successfully removed VM data from host'


  @staticmethod
  def __checkExists(libvirt_connection, name):
    """Check if a domain exists"""

    # Obtain array of all domains from libvirt
    all_domains = libvirt_connection.listAllDomains()

    # Determine if the name of any of the domains returned
    # matches the requested name
    if (any(domain.name() == name for domain in all_domains)):
      return True
    else:
      # VM does not exist
      return False


  @staticmethod
  def getVMDir(name):
    """Returns the storage directory for a given VM"""
    return McVirt.BASE_VM_STORAGE_DIR + '/' + name


  @staticmethod
  def getDiskPath(name, disk_number = 1):
    """Returns the path of a disk image for a given VM"""
    return VirtualMachine.getVMDir(name) + '/' + 'vm-%s-disk-%s.raw' % (name, disk_number)


  @staticmethod
  def create(libvirt_connection, name, cpu_cores, memory_allocation, disk_size, network_interfaces):
    """Creates a VM and returns the virtual_machine object for it"""

    # Validate the VM name
    valid_name_re = re.compile(r'[^a-z^0-9^A-Z-]').search
    if (bool(valid_name_re(name))):
      raise McVirtException('Error: Invalid VM Name - VM Name can only contain 0-9 a-Z and dashes')

    # Determine if VM already exists
    if (VirtualMachine.__checkExists(libvirt_connection, name)):
      raise McVirtException('Error: VM already exists')

    # Import domain XML template
    domain_xml = ET.parse(McVirt.TEMPLATE_DIR + '/domain.xml')

    # Add Name, RAM and CPU variables to XML
    domain_xml.find('./name').text = str(name)
    domain_xml.find('./memory').text = str(memory_allocation)
    domain_xml.find('./vcpu').text = str(cpu_cores)

    # Create directory for VM
    if (not os.path.exists(VirtualMachine.getVMDir(name))):
      os.makedirs(VirtualMachine.getVMDir(name))
    else:
      raise McVirtException('Error: VM directory already exists')

    # Create disk image
    disk_path = VirtualMachine.getDiskPath(name, 1)
    print 'Creating disk image'
    call(['dd', 'if=/dev/zero', 'of=%s' % disk_path, 'bs=1M', 'count=%s' % disk_size])

    # Set disk name in domain XML
    domain_xml.find('./devices/disk[@device="disk"]/source').set('dev', disk_path)

    # If any have been specified, add a network configuration for each of the
    # network interfaces to the domain XML
    if (network_interfaces != None):
      devices_xml = domain_xml.find('./devices')
      for network in network_interfaces:
        interface_xml = ET.SubElement(devices_xml, 'interface')
        interface_xml.set('type', 'network')

        # Create 'source'
        interface_source_xml = ET.SubElement(interface_xml, 'source')
        interface_source_xml.set('network', network)

        # Create 'model'
        interface_model_xml = ET.SubElement(interface_xml, 'model')
        interface_model_xml.set('type', 'virtio')

    # Register VM with LibVirt
    print 'Registering VM wth libvirt'
    domain_xml_string = ET.tostring(domain_xml.getroot(), encoding = 'utf8', method = 'xml')

    try:
      libvirt_connection.defineXML(domain_xml_string)
    except:
      raise McVirtException('Error: An error occured whilst registering VM')

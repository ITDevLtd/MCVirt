#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.mcvirt import McVirtException
from mcvirt.auth import Auth

import xml.etree.ElementTree as ET

class NetworkDoesNotExistException(McVirtException):
  """Network does not exist"""
  pass


class NetworkAlreadyExistsException(McVirtException):
  """Network already exists with the same name"""
  pass


class NetworkUtilizedException(McVirtException):
  """Network is utilized by virtual machines"""
  pass


class Network:
  """Provides an interface to LibVirt networks"""

  def __init__(self, mcvirt_object, name):
    """Sets member variables and obtains libvirt domain object"""
    self.mcvirt_object = mcvirt_object
    self.name = name

    # Ensure network exists
    if (not self._checkExists(mcvirt_object.getLibvirtConnection(), name)):
      raise NetworkDoesNotExistException('Network does not exist: %s' % name)

  def delete(self):
    """Deletes a network from the node"""
    # Ensure user has permission to manage networks
    self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

    # Ensure network is not connected to any VMs
    connected_vms = self._checkConnectedVirtualMachines()
    if (len(connected_vms)):
      connected_vm_name_string = ', '.join(vm.getName() for vm in connected_vms)
      raise NetworkUtilizedException('Network \'%s\' cannot be removed as it is used by the following VMs: %s'
        % (self.getName(), connected_vm_name_string))

    # Undefine object from libvirt
    try:
      self._getLibVirtObject().undefine()
    except:
      raise McVirtException('Failed to delete network from libvirt')

  def _checkConnectedVirtualMachines(self):
    """Returns an array of VM objects that have an interface connected to the network"""
    connected_vms = []

    # Iterate over all VMs and determine if any use the network to be deleted
    all_vm_objects = self.mcvirt_object.getAllVirtualMachineObjects()
    for vm_object in all_vm_objects:

      # Iterate over each network interface for the VM and determine if it
      # is connected to this network
      all_vm_interfaces = vm_object.getNetworkObjects()
      contains_connected_interface = False
      for network_interface in all_vm_interfaces:
        if (network_interface.getConnectedNetwork() == self.getName()):
          contains_connected_interface = True

      # If the VM contains at least one interface connected to the network,
      # add it to the array to be returned
      if (contains_connected_interface):
        connected_vms.append(vm_object)

    # Return array of VMs that use this network
    return connected_vms

  def _getLibVirtObject(self):
    """Returns the LibVirt object for the network"""
    return self.mcvirt_object.getLibvirtConnection().networkLookupByName(self.name)

  def getName(self):
    """Returns the name of the network"""
    return self.name

  @staticmethod
  def _checkExists(libvirt_connection, name):
    """Check if a network exists"""
    # Obtain array of all networks from libvirt
    all_networks = libvirt_connection.listAllNetworks()

    # Determine if the name of any of the networks returned
    # matches the requested name
    return (any(network.name() == name for network in all_networks))

  @staticmethod
  def create(mcvirt_object, name, physical_interface):
    """Creates a network on the node"""
    # Ensure user has permission to manage networks
    mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_HOST_NETWORKS)

    # Ensure network does not already exist
    if (Network._checkExists(mcvirt_object.getLibvirtConnection(), name)):
      raise NetworkAlreadyExistsException('Network already exists: %s' % name)

    # Create XML for network
    network_xml = ET.Element('network')
    network_xml.set('ipv6', 'no')
    network_name_xml = ET.SubElement(network_xml, 'name')
    network_name_xml.text = name

    # Create 'forward'
    network_forward_xml = ET.SubElement(network_xml, 'forward')
    network_forward_xml.set('mode', 'bridge')

    # Set interface bridge
    network_bridge_xml = ET.SubElement(network_xml, 'bridge')
    network_bridge_xml.set('name', physical_interface)

    # Convert XML object to string
    network_xml_string = ET.tostring(network_xml, encoding = 'utf8', method = 'xml')

    # Attempt to register network with LibVirt
    try:
      mcvirt_object.getLibvirtConnection().networkDefineXML(network_xml_string)
    except:
      raise McVirtException('An error occurred whilst registering network with LibVirt')
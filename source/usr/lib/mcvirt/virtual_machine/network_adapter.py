#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET

from mcvirt.mcvirt import McVirtException

class NetworkAdapter:
  """Provides operations to network interfaces attached to a VM"""

  def __init__(self, mac_address, domain_object):
    """Sets member variables and obtains libvirt domain object"""
    self.domain_object = domain_object
    self.mac_address = mac_address

  @staticmethod
  def createXML(network):
    """Creates a basic XML configuration for a network interface,
    encorporating the name of the network"""
    interface_xml = ET.Element('interface')
    interface_xml.set('type', 'network')

    # Create 'source'
    interface_source_xml = ET.SubElement(interface_xml, 'source')
    interface_source_xml.set('network', network)

    # Create 'model'
    interface_model_xml = ET.SubElement(interface_xml, 'model')
    interface_model_xml.set('type', 'virtio')

    return interface_xml

  def getConfig(self):
    domain_config = self.domain_object.getLibvirtConfig()
    interface_config = domain_config.find('./devices/interface[@type="network"]/mac[@address="%s"]/..' % self.mac_address)

    if (interface_config == None):
      raise McVirtException('Interface does not exist: %s' % self.mac_address)

    return interface_config

  def getConnectedNetwork(self):
    """Returns the network that a given interface is connected to"""
    interface_config = self.getConfig()
    network = interface_config.find('./source').get('network')
    return network

  @staticmethod
  def create(vm_object, network):
    """Add interface device to the given VM object, connected to the given network"""
    def updateXML(domain_xml):
      network_xml = NetworkAdapter.createXML(network)
      device_xml = domain_xml.find('./devices')
      device_xml.append(network_xml)

    vm_object.editConfig(updateXML)

  @staticmethod
  def delete(vm_object, mac_address):
    """Remove the given interface from the VM, based on the given MAC address"""
    def updateXML(domain_xml):
      device_xml = domain_xml.find('./devices')
      interface_xml = device_xml.find('./interface[@type="network"]/mac[@address="%s"]/..' % mac_address)

      if (interface_xml == None):
        raise McVirtException('Not interface with MAC address \'%s\' attached to VM' % mac_address)

      device_xml.remove(interface_xml)

    vm_object.editConfig(updateXML)
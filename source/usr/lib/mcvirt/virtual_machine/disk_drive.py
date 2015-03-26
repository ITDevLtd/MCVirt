#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET
import os

from mcvirt.mcvirt import McVirtException, McVirt

class DiskDrive:
  """Provides operations to manage the disk drive attached to a VM"""

  def __init__(self, vm_object):
    """Sets member variables and obtains libvirt domain object"""
    self.vm_object = vm_object

  def attachISO(self, iso_file):
    """Attaches an ISO image to the disk drive of the VM"""

    # Ensure that the ISO image exists
    full_path = McVirt.ISO_STORAGE_DIR + '/' + iso_file
    if (not os.path.isfile(full_path)):
      raise McVirtException('ISO image not found: %s' % iso_file)

    # Import cdrom XML template
    cdrom_xml = ET.parse(McVirt.TEMPLATE_DIR + '/cdrom.xml')

    # Add iso image path to cdrom XML
    cdrom_xml.find('source').set('file', full_path)
    cdrom_xml_string = ET.tostring(cdrom_xml.getroot(), encoding = 'utf8', method = 'xml')

    # Update the libvirt cdrom device
    if (not self.vm_object._getLibvirtDomainObject().updateDeviceFlags(cdrom_xml_string)):
      print 'Attached ISO %s' % iso_file
    else:
      raise McVirtException('An error occurred whilst attaching ISO')

  def removeISO(self):
    """Removes ISO attached to the disk drive of a VM"""

    # Import cdrom XML template
    cdrom_xml = ET.parse(McVirt.TEMPLATE_DIR + '/cdrom.xml')

    # Add iso image path to cdrom XML
    cdrom_xml = cdrom_xml.getroot()
    source_xml = cdrom_xml.find('source')

    if (source_xml is not None):
      cdrom_xml.remove(source_xml)
      cdrom_xml_string = ET.tostring(cdrom_xml, encoding = 'utf8', method = 'xml')

      # Update the libvirt cdrom device
      if (self.vm_object._getLibvirtDomainObject().updateDeviceFlags(cdrom_xml_string)):
        raise McVirtException('An error occurred whilst detaching ISO')

  def getCurrentDisk(self):
    """Returns the path of the disk currently attached to the VM"""

    # Import cdrom XML template
    domain_config = self.vm_object.getLibvirtConfig()
    source_xml = domain_config.find('./devices/disk[@device="cdrom"]/source')

    if (source_xml is not None):
      return source_xml.get('file')
    else:
      return None
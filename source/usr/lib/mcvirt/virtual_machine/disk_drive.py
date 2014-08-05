#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import xml.etree.ElementTree as ET
import os

from mcvirt.mcvirt import McVirtException

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
    if (not self.vm_object.domain_object.updateDeviceFlags(cdrom_xml_string)):
      print 'Attached ISO %s' % iso_file
    else:
      raise McVirtException('An error occured whilst attaching ISO')

# Copyright (c) 2014 - I.T. Dev Ltd
#
# This file is part of MCVirt.
#
# MCVirt is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# MCVirt is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/>

import libvirt
import xml.etree.ElementTree as ET
import os

from mcvirt.mcvirt import MCVirtException, MCVirt
from mcvirt.iso import Iso


class DiskDrive:
    """Provides operations to manage the disk drive attached to a VM"""

    def __init__(self, vm_object):
        """Sets member variables and obtains libvirt domain object"""
        self.vm_object = vm_object

    def attachISO(self, iso_object):
        """Attaches an ISO image to the disk drive of the VM"""

        # Import cdrom XML template
        cdrom_xml = ET.parse(MCVirt.TEMPLATE_DIR + '/cdrom.xml')

        # Add iso image path to cdrom XML
        cdrom_xml.find('source').set('file', iso_object.getPath())
        cdrom_xml_string = ET.tostring(cdrom_xml.getroot(), encoding='utf8', method='xml')

        # Update the libvirt cdrom device
        if (not self.vm_object._getLibvirtDomainObject().updateDeviceFlags(cdrom_xml_string)):
            print 'Attached ISO %s' % iso_object.getName()
        else:
            raise MCVirtException('An error occurred whilst attaching ISO')

    def removeISO(self):
        """Removes ISO attached to the disk drive of a VM"""

        # Import cdrom XML template
        cdrom_xml = ET.parse(MCVirt.TEMPLATE_DIR + '/cdrom.xml')

        # Add iso image path to cdrom XML
        cdrom_xml = cdrom_xml.getroot()
        source_xml = cdrom_xml.find('source')

        if (source_xml is not None):
            cdrom_xml.remove(source_xml)
            cdrom_xml_string = ET.tostring(cdrom_xml, encoding='utf8', method='xml')

            # Update the libvirt cdrom device
            if (self.vm_object._getLibvirtDomainObject().updateDeviceFlags(cdrom_xml_string)):
                raise MCVirtException('An error occurred whilst detaching ISO')

    def getCurrentDisk(self):
        """Returns the path of the disk currently attached to the VM"""

        # Import cdrom XML template
        domain_config = self.vm_object.getLibvirtConfig()
        source_xml = domain_config.find('./devices/disk[@device="cdrom"]/source')

        if (source_xml is not None):
            filename = Iso.getFilenameFromPath(source_xml.get('file'))
            return Iso(self.vm_object.mcvirt_object, filename)
        else:
            return None

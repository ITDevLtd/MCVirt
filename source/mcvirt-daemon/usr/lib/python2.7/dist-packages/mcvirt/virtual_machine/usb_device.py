# Copyright (c) 2016 - I.T. Dev Ltd
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

import xml.etree.ElementTree as ET
import libvirt

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.constants import DirectoryLocation
from mcvirt.exceptions import VmStoppedException


class UsbDevice(PyroObject):
    """Provide methods for attaching USB devices to VMs"""

    def __init__(self, bus, device, virtual_machine):
        """Set member variables for the object"""
        self.virtual_machine = virtual_machine
        self.bus = bus
        self.device = device

    def _generate_libvirt_xml(self):
        """Generate LibVirt XML for the device"""
        usb_xml = ET.parse(DirectoryLocation.TEMPLATE_DIR + '/usb-device.xml')
        usb_xml.find('./source/address').set('bus', self.bus)
        usb_xml.find('./source/address').set('device', self.device)
        return ET.tostring(usb_xml.getroot(), encoding='utf8', method='xml')

    def get_bus(self):
        """Return the bus for the USB object"""
        return int(self.bus)

    def get_device(self):
        """Return the device ID of the USB object"""
        return int(self.device)

    @Expose(locking=True)
    def attach(self):
        """Attach the USB device to the libvirt domain"""
        if not self.virtual_machine.is_running:
            raise VmStoppedException('VM is stopped. '
                                     'Can only attached USB device to running VM')
        # TO ADD PERMISSION CHECKING
        libvirt_object = self.virtual_machine.get_libvirt_domain_object()
        libvirt_object.attachDeviceFlags(
            self._generate_libvirt_xml(),
            (libvirt.VIR_DOMAIN_AFFECT_LIVE |
             libvirt.VIR_DOMAIN_AFFECT_CURRENT |
             libvirt.VIR_DOMAIN_AFFECT_CONFIG))

    @Expose(locking=True)
    def detach(self):
        """Detach the USB device from the libvirt domain"""
        if not self.virtual_machine.is_running:
            raise VmStoppedException('VM is stopped. '
                                     'Can only attached USB device to running VM')

        # TO ADD PERMISSION CHECKING
        libvirt_object = self.virtual_machine.get_libvirt_domain_object()
        libvirt_object.detachDeviceFlags(
            self._generate_libvirt_xml(),
            (libvirt.VIR_DOMAIN_AFFECT_LIVE |
             libvirt.VIR_DOMAIN_AFFECT_CURRENT |
             libvirt.VIR_DOMAIN_AFFECT_CONFIG))

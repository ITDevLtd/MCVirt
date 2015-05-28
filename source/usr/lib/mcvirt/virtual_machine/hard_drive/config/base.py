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

import xml.etree.ElementTree as ET

from mcvirt.mcvirt import MCVirtException
from mcvirt.virtual_machine.hard_drive.base import Base as HardDriveBase
from mcvirt.mcvirt_config import MCVirtConfig

class ReachedMaximumStorageDevicesException(MCVirtException):
    """Reached the limit to number of hard disks attached to VM"""
    pass


class Base(object):
    """Provides a base for storage configurations"""

    SNAPSHOT_SUFFIX = '_snapshot'
    SNAPSHOT_SIZE = '500M'

    def __init__(self, vm_object, disk_id=None, config=None, registered=False):
        """Set member variables and obtains the stored configuration"""
        self.config['disk_id'] = disk_id
        self.vm_object = vm_object

        # If a configuration hash has been passed, overwrite all
        # member variable configurations with it.
        if (config):
            self.config = config

        # If the disk is configured on a VM, obtain
        # the details from the VM configuration
        if (registered):
            disk_config = self.getDiskConfig()
            for config_key in disk_config:
                self.config[config_key] = disk_config[config_key]

    def _dumpConfig(self):
        """Dumps all required configuration to be able to recreate the
           config object on a remote node"""
        dump_config = \
          {
            'config': self.config,
            'vm_name': self.vm_object.getName(),
            'storage_type': self._getType()
          }
        return dump_config

    def _getType(self):
        """Returns the type of storage for the hard drive"""
        return self.__class__.__name__

    def getMaximumDevices(self):
        """Returns the maximum number of storage devices for the current type"""
        return self.MAXIMUM_DEVICES

    def _getVolumeGroup(self):
        """Returns the node MCVirt volume group"""
        return MCVirtConfig().getConfig()['vm_storage_vg']

    def getDiskConfig(self):
        """Returns the disk configuration for the hard drive"""
        vm_config = self.vm_object.getConfigObject().getConfig()
        return vm_config['hard_disks'][str(self.getId())]

    def getId(self):
        """Returns the disk ID of the current disk, generating a new one
           if there is not already one present"""
        if (self.config['disk_id'] is None):
            self.config['disk_id'] = self._getAvailableId()

        return self.config['disk_id']

    def _getTargetDev(self):
        """Determines the target dev, based on the disk's ID"""
        # Use ascii numbers to map 1 => a, 2 => b, etc...
        return 'sd' + chr(96 + int(self.getId()))

    def _getAvailableId(self):
        """Obtains the next available ID for the VM hard drive, by scanning the IDs
        of disks attached to the VM"""
        found_available_id = False
        disk_id = 0
        vm_config = self.vm_object.getConfigObject().getConfig()
        disks = vm_config['hard_disks']
        while (not found_available_id):
            disk_id += 1
            if (not str(disk_id) in disks):
                found_available_id = True

        # Check that the id is less than 4, as a VM can only have a maximum of 4 disks
        if (int(disk_id) > self.getMaximumDevices()):
            raise ReachedMaximumStorageDevicesException('A maximum of %s hard drives can be mapped to a VM' % self.getMaximumDevices())

        return disk_id

    def _getLogicalVolumePath(self, name):
        """Returns the full path of a given logical volume"""
        volume_group = self._getVolumeGroup()
        return '/dev/' + volume_group + '/' + name

    def _generateLibvirtXml(self):
        """Creates a basic libvirt XML configuration for the connection to the disk"""
        # Create the base disk XML element
        device_xml = ET.Element('disk')
        device_xml.set('type', 'block')
        device_xml.set('device', 'disk')

        # Configure the interface driver to the disk
        driver_xml = ET.SubElement(device_xml, 'driver')
        driver_xml.set('name', 'qemu')
        driver_xml.set('type', 'raw')
        driver_xml.set('cache', 'none')

        # Configure the source of the disk
        source_xml = ET.SubElement(device_xml, 'source')
        source_xml.set('dev', self._getDiskPath())

        # Configure the target
        target_xml = ET.SubElement(device_xml, 'target')
        target_xml.set('dev', '%s' % self._getTargetDev())
        target_xml.set('bus', 'virtio')

        return device_xml

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        raise NotImplementedError

    def _getMCVirtConfig(self):
        """Returns the MCVirt configuration for the hard drive object"""
        raise NotImplementedError

    def _getBackupLogicalVolume(self):
        """Returns the storage device for the backup"""
        raise NotImplementedError

    def _getBackupSnapshotLogicalVolume(self):
        """Returns the logical volume name for the backup snapshot"""
        raise NotImplementedError

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

import Pyro4
import os
import xml.etree.ElementTree as ET
from enum import Enum

from mcvirt.exceptions import (HardDriveDoesNotExistException,
                               StorageTypesCannotBeMixedException,
                               LogicalVolumeDoesNotExistException,
                               BackupSnapshotAlreadyExistsException,
                               BackupSnapshotDoesNotExistException,
                               ExternalStorageCommandErrorException,
                               MCVirtCommandException)
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import ReachedMaximumStorageDevicesException
from mcvirt.utils import get_hostname
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import lockingMethod


class Driver(Enum):
    """Enums for specifying the hard drive driver type"""
    VIRTIO = 'virtio'
    IDE = 'ide'
    SCSI = 'scsi'
    USB = 'usb'
    SATA = 'sata'
    SD = 'sd'


class Base(PyroObject):
    """Provides base operations to manage all hard drives, used by VMs"""

    # The maximum number of storage devices for the current type
    MAXIMUM_DEVICES = 1

    # The default driver for the disk
    DEFAULT_DRIVER = Driver.IDE.name

    # Set default options for snapshotting
    SNAPSHOT_SUFFIX = '_snapshot'
    SNAPSHOT_SIZE = '500M'

    def __init__(self, vm_object, disk_id=None, driver=None):
        """Sets member variables"""
        self._disk_id = disk_id
        self._driver = driver
        self.vm_object = vm_object

        # If the disk is configured on a VM, obtain
        # the details from the VM configuration
        disk_config = self.getDiskConfig()
        for key, value in self.getDiskConfig().iteritems():
            setattr(self, key, value)

    @property
    def config_properties(self):
        """Returns the disk object config items"""
        return ['disk_id', 'driver']

    def __setattr__(self, name, value):
        """Override setattr to ensure that the value of
           a disk config item is written to, rather than the
           property method"""
        if name in self.config_properties:
            name = '_%s' % name
        return super(Base, self).__setattr__(name, value)

    @property
    def disk_id(self):
        """Returns the disk ID of the current disk, generating a new one
           if there is not already one present"""
        if self._disk_id is None:
            self._disk_id = self._getAvailableId()
        return self._disk_id

    @property
    def _target_dev(self):
        """Determines the target dev, based on the disk's ID"""
        # Use ascii numbers to map 1 => a, 2 => b, etc...
        return 'sd' + chr(96 + int(self.disk_id))

    @property
    def driver(self):
        """Returns the disk drive driver name"""
        if self._driver is None:
            self._driver = self.DEFAULT_DRIVER
        return self._driver

    def getRemoteObject(self, node_name=None, remote_node=None, registered=True):
        cluster = self._get_registered_object('cluster')
        if remote_node is None:
            remote_node = cluster.getRemoteNode(node_name)

        remote_vm_factory = remote_node.getConnection('virtual_machine_factory')
        remote_vm = remote_vm_factory.getVirtualMachineByName(self.vm_object.getName())
        remote_hard_drive_factory = remote_node.getConnection('hard_drive_factory')

        kwargs = {
            'vm_object': remote_vm,
            'disk_id': self.disk_id
        }
        if not registered:
            kwargs['storage_type'] = self.getType()
            for config in self.config_properties:
                kwargs[config] = getattr(self, config)

        hard_drive_object = remote_hard_drive_factory.getObject(**kwargs)
        remote_node.annotateObject(hard_drive_object)
        return hard_drive_object


    def _getAvailableId(self):
        """Obtains the next available ID for the VM hard drive, by scanning the IDs
           of disks attached to the VM"""
        found_available_id = False
        disk_id = 0
        vm_config = self.vm_object.getConfigObject().getConfig()
        disks = vm_config['hard_disks']
        while (not found_available_id):
            disk_id += 1
            if not str(disk_id) in disks:
                found_available_id = True

        # Check that the id is less than 4, as a VM can only have a maximum of 4 disks
        if int(disk_id) > self.MAXIMUM_DEVICES:
            raise ReachedMaximumStorageDevicesException(
                'A maximum of %s hard drives can be mapped to a VM' %
                self.MAXIMUM_DEVICES)

        return disk_id

    def _ensureExists(self):
        """Ensures the disk exists on the local node"""
        if not self._checkExists():
            raise HardDriveDoesNotExistException(
                'Disk %s for %s does not exist' %
                (self.disk_id, self.vm_object.getName()))

    def getType(self):
        """Returns the type of storage for the hard drive"""
        return self.__class__.__name__

    def delete(self):
        """Deletes the logical volume for the disk"""
        self._ensureExists()

        if self.vm_object.isRegisteredLocally():
            # Remove from LibVirt, if registered, so that libvirt doesn't
            # hold the device open when the storage is removed
            self._unregisterLibvirt()

        # Remove backing storage
        self._removeStorage()

        # Remove the hard drive from the MCVirt VM configuration
        self.removeFromVirtualMachine(unregister=False)

    def duplicate(self, destination_vm_object):
        """Clone the hard drive and attach it to the new VM object"""
        self._ensureExists()
        disk_size = self.getSize()

        # Create new disk object, using the same type, size and disk_id
        new_disk_object = self._get_registered_object('hard_drive_factory').getClass(
            self.getType()).create(
            destination_vm_object,
            disk_size,
            disk_id=self.disk_id,
            driver=self.driver)

        source_drbd_block_device = self._getDiskPath()
        destination_drbd_block_device = new_disk_object._getDiskPath()

        # Use dd to duplicate the old disk to the new disk
        command_args = ('dd', 'if=%s' % source_drbd_block_device,
                        'of=%s' % destination_drbd_block_device, 'bs=1M')
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            new_disk_object.delete()
            raise ExternalStorageCommandErrorException(
                "Error whilst duplicating disk logical volume:\n" + str(e)
            )

        return new_disk_object

    @Pyro4.expose()
    @lockingMethod()
    def addToVirtualMachine(self, register=True):
        """Add the hard drive to the virtual machine,
           and performs the base function on all nodes in the cluster"""
        # Update the libvirt domain XML configuration
        if self.vm_object.isRegisteredLocally():
            self._registerLibvirt()

        # Update the VM storage config
        self._setVmStorageType()

        # Update VM config file
        def addDiskToConfig(vm_config):
            vm_config['hard_disks'][str(self.disk_id)] = self._getMCVirtConfig()

        self.vm_object.getConfigObject().updateConfig(
            addDiskToConfig, 'Added disk \'%s\' to \'%s\'' %
                             (self.disk_id, self.vm_object.getName())
        )

        # If the node cluster is initialised, update all remote node configurations
        if self._is_cluster_master:

            # Create list of nodes that the hard drive was successfully added to
            successful_nodes = []
            cluster = self._get_registered_object('cluster')
            try:
                for node in cluster.getNodes():
                    remote_disk_object = self.getRemoteObject(node, registered=False)
                    remote_disk_object.addToVirtualMachine()
                    successful_nodes.append(node)
            except Exception:
                # If the hard drive fails to be added to a node, remove it from all successful nodes
                # and remove from the local node
                for node in successful_nodes:
                    self.getRemoteObject(node).removeFromVirtualMachine()

                self.removeFromVirtualMachine(unregister=register, all_nodes=False)
                raise

    @staticmethod
    def isAvailable(pyro_object):
        """Returns whether the storage type is available on the node"""
        raise NotImplementedError

    @Pyro4.expose()
    @lockingMethod()
    def removeFromVirtualMachine(self, unregister=False, all_nodes=True):
        """Remove the hard drive from a VM configuration and perform all nodes
           in the cluster"""
        # If the VM that the hard drive is attached to is registered on the local
        # node, remove the hard drive from the LibVirt configuration
        if unregister and self.vm_object.isRegisteredLocally():
            self._unregisterLibvirt()

        # Update VM config file
        def removeDiskFromConfig(vm_config):
            del(vm_config['hard_disks'][str(self.disk_id)])

        self.vm_object.getConfigObject().updateConfig(
            removeDiskFromConfig, 'Removed disk \'%s\' from \'%s\'' %
            (self.disk_id, self.vm_object.getName()))

        # If the cluster is initialised, run on all nodes that the VM is available on
        if self._is_cluster_master and all_nodes:
            cluster = self._get_registered_object('cluster')
            for node in cluster.getNodes():
                remote_disk_object = self.getRemoteObject(node)
                remote_disk_object.removeFromVirtualMachine()


    def _unregisterLibvirt(self):
        """Removes the hard drive from the LibVirt configuration for the VM"""
        # Update the libvirt domain XML configuration
        def updateXML(domain_xml):
            device_xml = domain_xml.find('./devices')
            disk_xml = device_xml.find(
                './disk/target[@dev="%s"]/..' %
                self._target_dev)
            device_xml.remove(disk_xml)

        # Update libvirt configuration
        self.vm_object.editConfig(updateXML)

    def _registerLibvirt(self):
        """Register the hard drive with the Libvirt VM configuration"""

        def updateXML(domain_xml):
            drive_xml = self._generateLibvirtXml()
            device_xml = domain_xml.find('./devices')
            device_xml.append(drive_xml)

        # Update libvirt configuration
        self.vm_object.editConfig(updateXML)

    def _setVmStorageType(self):
        """Set the VM configuration storage type to the current hard drive type"""
        # Ensure VM has not already been configured with disks that
        # do not match the type specified
        number_of_disks = len(self.vm_object.getHardDriveObjects())
        current_storage_type = self.vm_object.getConfigObject(
        ).getConfig()['storage_type']
        if current_storage_type != self.getType():
            if number_of_disks:
                raise StorageTypesCannotBeMixedException(
                    'The VM (%s) is already configured with %s disks' %
                    (self.vm_object.getName(), current_storage_type))

            def updateStorageTypeConfig(config):
                config['storage_type'] = self.getType()
            self.vm_object.getConfigObject().updateConfig(
                updateStorageTypeConfig, 'Updated storage type for \'%s\' to \'%s\'' %
                (self.vm_object.getName(), self.getType()))

    @Pyro4.expose()
    @lockingMethod()
    def createLogicalVolume(self, *args, **kwargs):
        """Provides an exposed method for _createLogicalVolume
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._createLogicalVolume(*args, **kwargs)

    def _createLogicalVolume(self, name, size, perform_on_nodes=False):
        """Creates a logical volume on the node/cluster"""
        volume_group = self._getVolumeGroup()

        # Create command list
        command_args = ['/sbin/lvcreate', volume_group, '--name', name, '--size', '%sM' % size]
        try:
            # Create on local node
            System.runCommand(command_args)

            if perform_on_nodes and self._is_cluster_master:
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.createLogicalVolume(name=name, size=size)

                cluster = self._get_registered_object('cluster')
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=self.vm_object._getRemoteNodes())

        except MCVirtCommandException, e:
            # Remove any logical volumes that had been created if one of them fails
            self._removeLogicalVolume(
                name,
                ignore_non_existent=True,
                perform_on_nodes=perform_on_nodes)
            raise ExternalStorageCommandErrorException(
                "Error whilst creating disk logical volume:\n" + str(e)
            )

    @Pyro4.expose()
    @lockingMethod()
    def removeLogicalVolume(self, *args, **kwargs):
        """Provides an exposed method for _removeLogicalVolume
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._removeLogicalVolume(*args, **kwargs)

    def _removeLogicalVolume(self, name, ignore_non_existent=False,
                             perform_on_nodes=False):
        """Removes a logical volume from the node/cluster"""
        # Create command arguments
        command_args = ['lvremove', '-f', self._getLogicalVolumePath(name)]
        try:
            # Determine if logical volume exists before attempting to remove it
            if (not (ignore_non_existent and
                     not self._checkLogicalVolumeExists(name))):
                System.runCommand(command_args)

            if perform_on_nodes and self._is_cluster_master:
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.removeLogicalVolume(
                        name=name, ignore_non_existent=ignore_non_existent
                    )

                cluster = self._get_registered_object('cluster')
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=self.vm_object._getRemoteNodes())

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst removing disk logical volume:\n" + str(e)
            )

    def _getLogicalVolumeSize(self, name):
        """Obtains the size of a logical volume"""
        # Use 'lvs' to obtain the size of the disk
        command_args = (
            'lvs',
            '--nosuffix',
            '--noheadings',
            '--units',
            'm',
            '--options',
            'lv_size',
            self._getLogicalVolumePath(name))
        try:
            (_, command_output, _) = System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst obtaining the size of the logical volume:\n" +
                str(e))

        lv_size = command_output.strip().split('.')[0]
        return int(lv_size)

    @Pyro4.expose()
    @lockingMethod()
    def zeroLogicalVolume(self, *args, **kwargs):
        """Provides an exposed method for _zeroLogicalVolume
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._zeroLogicalVolume(*args, **kwargs)

    def _zeroLogicalVolume(self, name, size, perform_on_nodes=False):
        """Blanks a logical volume by filling it with null data"""
        # Obtain the path of the logical volume
        lv_path = self._getLogicalVolumePath(name)

        # Create command arguments
        command_args = ['dd', 'if=/dev/zero', 'of=%s' % lv_path, 'bs=1M', 'count=%s' % size,
                        'conv=fsync', 'oflag=direct']
        try:
            # Create logical volume on local node
            System.runCommand(command_args)

            if perform_on_nodes and self._is_cluster_master:
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.zeroLogicalVolume(name=name, size=size)

                cluster = self._get_registered_object('cluster')
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=self.vm_object._getRemoteNodes())

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst zeroing logical volume:\n" + str(e)
            )

    def _ensureLogicalVolumeExists(self, name):
        """Ensures that a logical volume exists, throwing an exception if it does not"""
        if not self._checkLogicalVolumeExists(name):
            raise LogicalVolumeDoesNotExistException(
                'Logical volume %s does not exist on %s' %
                (name, get_hostname()))

    def _checkLogicalVolumeExists(self, name):
        """Determines if a logical volume exists, returning 1 if present and 0 if not"""
        return os.path.lexists(self._getLogicalVolumePath(name))

    def _ensureLogicalVolumeActive(self, name):
        """Ensures that a logical volume is active"""
        if not self._checkLogicalVolumeActive(name):
            raise LogicalVolumeIsNotActive(
                'Logical volume %s is not active on %s' %
                (name, get_hostname()))

    def _checkLogicalVolumeActive(self, name):
        """Checks that a logical volume is active"""
        return os.path.exists(self._getLogicalVolumePath(name))

    @Pyro4.expose()
    @lockingMethod()
    def activateLogicalVolume(self, *args, **kwargs):
        """Provides an exposed method for _activateLogicalVolume
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._activateLogicalVolume(*args, **kwargs)

    def _activateLogicalVolume(self, name, perform_on_nodes=False):
        """Activates a logical volume on the node/cluster"""
        # Obtain logical volume path
        lv_path = self._getLogicalVolumePath(name)

        # Create command arguments
        command_args = ['lvchange', '-a', 'y', '--yes', lv_path]
        try:
            # Run on the local node
            System.runCommand(command_args)

            if perform_on_nodes and self._is_cluster_master:
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.activateLogicalVolume(name=name)

                cluster = self._get_registered_object('cluster')
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=self.vm_object._getRemoteNodes())

        except MCVirtCommandException, e:
            raise ExternalStorageCommandErrorException(
                "Error whilst activating logical volume:\n" + str(e)
            )

    def createBackupSnapshot(self):
        """Creates a snapshot of the logical volume for backing up and locks the VM"""
        self._ensureExists()
        from mcvirt.virtual_machine.virtual_machine import LockStates
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assertPermission(
            PERMISSIONS.BACKUP_VM,
            self.vm_object
        )

        # Ensure VM is registered locally
        self.vm_object.ensureRegisteredLocally()

        # Obtain logical volume names/paths
        backup_volume_path = self._getLogicalVolumePath(
            self._getBackupLogicalVolume())
        snapshot_logical_volume = self._getBackupSnapshotLogicalVolume()

        # Determine if logical volume already exists
        if self._checkLogicalVolumeActive(snapshot_logical_volume):
            raise BackupSnapshotAlreadyExistsException(
                'The backup snapshot for \'%s\' already exists: %s' %
                (backup_volume_path, snapshot_logical_volume)
            )

        # Lock the VM
        self.vm_object.setLockState(LockStates.LOCKED)

        try:
            System.runCommand(['lvcreate', '--snapshot', backup_volume_path,
                               '--name', self._getBackupSnapshotLogicalVolume(),
                               '--size', self.SNAPSHOT_SIZE])
            return self._getLogicalVolumePath(snapshot_logical_volume)
        except:
            self.vm_object.setLockState(LockStates.UNLOCKED)
            raise

    def deleteBackupSnapshot(self):
        """Deletes the backup snapshot for the disk and unlocks the VM"""
        self._ensureExists()
        from mcvirt.virtual_machine.virtual_machine import LockStates
        # Ensure the user has permission to delete snapshot backups
        self._get_registered_object('auth').assertPermission(
            PERMISSIONS.BACKUP_VM,
            self.vm_object
        )

        # Ensure the snapshot logical volume exists
        if not self._checkLogicalVolumeActive(self._getBackupSnapshotLogicalVolume()):
            raise BackupSnapshotDoesNotExistException(
                'The backup snapshot for \'%s\' does not exist' %
                self._getLogicalVolumePath(config._getBackupLogicalVolume())
            )

        System.runCommand(['lvremove', '-f',
                           self._getLogicalVolumePath(self._getBackupSnapshotLogicalVolume())])

        # Unlock the VM
        self.vm_object.setLockState(LockStates.UNLOCKED)

    @Pyro4.expose()
    @lockingMethod()
    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        raise NotImplementedError

    def _checkExists(self):
        """Checks if the disk exists"""
        raise NotImplementedError

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        raise NotImplementedError

    def create(self):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        raise NotImplementedError

    def activateDisk(self):
        """Activates the storage volume"""
        raise NotImplementedError

    def deactivateDisk(self):
        """Deactivates the storage volume"""
        raise NotImplementedError

    def preMigrationChecks(self, destination_node):
        """Determines if the disk is in a state to allow the attached VM
           to be migrated to another node"""
        raise NotImplementedError

    def preOnlineMigration(self):
        """Performs required tasks in order
           for the underlying VM to perform an
           online migration"""
        raise NotImplementedError

    def postOnlineMigration(self):
        """Performs post tasks after a VM
           has performed an online migration"""
        raise NotImplementedError

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        raise NotImplementedError

    def move(self, destination_node, source_node):
        """Moves the storage to another node in the cluster"""
        raise NotImplementedError

    def _getVolumeGroup(self):
        """Returns the node MCVirt volume group"""
        return MCVirtConfig().getConfig()['vm_storage_vg']

    def getDiskConfig(self):
        """Returns the disk configuration for the hard drive"""
        vm_config = self.vm_object.getConfigObject().getConfig()
        if str(self.disk_id) in vm_config['hard_disks']:
            return vm_config['hard_disks'][str(self.disk_id)]
        else:
            return {}

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
        driver_xml.set('cache', self.CACHE_MODE)

        # Configure the source of the disk
        source_xml = ET.SubElement(device_xml, 'source')
        source_xml.set('dev', self._getDiskPath())

        # Configure the target
        target_xml = ET.SubElement(device_xml, 'target')
        target_xml.set('dev', '%s' % self._target_dev)
        target_xml.set('bus', self._getLibvirtDriver())

        return device_xml

    def _getLibvirtDriver(self):
        """Returns the libvirt name of the driver for the disk"""
        return Driver[self.driver].value

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        raise NotImplementedError

    def _getMCVirtConfig(self):
        """Returns the MCVirt configuration for the hard drive object"""
        config = {
            'driver': self.driver
        }
        return config

    def _getBackupLogicalVolume(self):
        """Returns the storage device for the backup"""
        raise NotImplementedError

    def _getBackupSnapshotLogicalVolume(self):
        """Returns the logical volume name for the backup snapshot"""
        raise NotImplementedError

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

from mcvirt.mcvirt import MCVirtException
import os
from mcvirt.system import System, MCVirtCommandException


class HardDriveDoesNotExistException(MCVirtException):
    """The given hard drive does not exist"""
    pass


class StorageTypesCannotBeMixedException(MCVirtException):
    """Storage types cannot be mixed within a single VM"""
    pass


class LogicalVolumeDoesNotExistException(MCVirtException):
    """A required logical volume does not exist"""
    pass


class BackupSnapshotAlreadyExistsException(MCVirtException):
    """The backup snapshot for the logical volume already exists"""
    pass


class BackupSnapshotDoesNotExistException(MCVirtException):
    """The backup snapshot for the logical volume does not exist"""
    pass


class Base(object):
    """Provides base operations to manage all hard drives, used by VMs"""

    def __init__(self, disk_id):
        """Sets member variables"""
        if (not self._checkExists()):
            raise HardDriveDoesNotExistException(
                'Disk %s for %s does not exist' %
                (self.getConfigObject().getId(), self.getVmObject().name))

    def getConfigObject(self):
        """Returns the config object for the hard drive"""
        return self.config

    def getVmObject(self):
        """Returns the VM object that the hard drive is attached to"""
        return self.getConfigObject().vm_object

    def getType(self):
        """Returns the type of storage for the hard drive"""
        return self.__class__.__name__

    def delete(self):
        """Deletes the logical volume for the disk"""
        from mcvirt.virtual_machine.hard_drive.factory import Factory
        # Remove from LibVirt, if registered, so that libvirt doesn't
        # hold the device open when the storage is removed
        Factory.getClass(self.getType())._unregisterLibvirt(self.getConfigObject())

        # Remove backing storage
        self._removeStorage()

        # Remove the hard drive from the MCVirt VM configuration
        Factory.getClass(
            self.getType())._removeFromVirtualMachine(
            self.getConfigObject(),
            unregister=False)

    def duplicate(self, destination_vm_object):
        """Clone the hard drive and attach it to the new VM object"""
        from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
        disk_size = self.getSize()

        # Create new disk object, using the same type, size and disk_id
        new_disk_object = HardDriveFactory.getClass(
            self.getType()).create(
            destination_vm_object,
            disk_size,
            disk_id=self.getConfigObject().getId())

        source_drbd_block_device = self.getConfigObject()._getDiskPath()
        destination_drbd_block_device = new_disk_object.getConfigObject()._getDiskPath()

        # Use dd to duplicate the old disk to the new disk
        command_args = (
            'dd',
            'if=%s' %
            source_drbd_block_device,
            'of=%s' %
            destination_drbd_block_device,
            'bs=1M')
        try:
            System.runCommand(command_args)
        except MCVirtCommandException, e:
            new_disk_object.delete()
            raise MCVirtException("Error whilst duplicating disk logical volume:\n" + str(e))

        return new_disk_object

    @staticmethod
    def _removeFromVirtualMachine(config_object, unregister=False):
        """Removes the hard drive configuration from the MCVirt VM configuration"""
        # If the VM that the hard drive is attached to is registered on the local
        # node, remove the hard drive from the LibVirt configuration
        if (unregister and config_object.vm_object.isRegisteredLocally()):
            Base._unregisterLibvirt(config_object)

        # Update VM config file
        def removeDiskFromConfig(vm_config):
            del(vm_config['hard_disks'][str(config_object.getId())])

        config_object.vm_object.getConfigObject().updateConfig(
            removeDiskFromConfig, 'Removed disk \'%s\' from \'%s\'' %
            (config_object.getId(), config_object.vm_object.getName()))

    @staticmethod
    def _unregisterLibvirt(config_object):
        """Removes the hard drive from the LibVirt configuration for the VM"""
        # Update the libvirt domain XML configuration
        def updateXML(domain_xml):
            device_xml = domain_xml.find('./devices')
            disk_xml = device_xml.find(
                './disk/target[@dev="%s"]/..' %
                config_object._getTargetDev())
            device_xml.remove(disk_xml)

        # Update libvirt configuration
        config_object.vm_object.editConfig(updateXML)

    @staticmethod
    def _addToVirtualMachine(config_object):
        """Adds the current disk to a give VM"""
        from mcvirt.virtual_machine.hard_drive.factory import Factory

        # Update the libvirt domain XML configuration
        if (config_object.vm_object.isRegisteredLocally()):
            Factory.getClass(config_object._getType())._registerLibvirt(config_object)

        # Update the VM storage config
        Factory.getClass(config_object._getType())._setVmStorageType(config_object)

        # Update VM config file
        def addDiskToConfig(vm_config):
            vm_config['hard_disks'][str(config_object.getId())] = config_object._getMCVirtConfig()

        config_object.vm_object.getConfigObject().updateConfig(
            addDiskToConfig, 'Added disk \'%s\' to \'%s\'' %
            (config_object.getId(), config_object.vm_object.getName()))

    @staticmethod
    def _registerLibvirt(config_object):
        """Register the hard drive with the Libvirt VM configuration"""

        def updateXML(domain_xml):
            drive_xml = config_object._generateLibvirtXml()
            device_xml = domain_xml.find('./devices')
            device_xml.append(drive_xml)

        # Update libvirt configuration
        config_object.vm_object.editConfig(updateXML)

    @staticmethod
    def _setVmStorageType(config_object):
        """Set the VM configuration storage type to the current hard drive type"""
        # Ensure VM has not already been configured with disks that
        # do not match the type specified
        number_of_disks = len(config_object.vm_object.getDiskObjects())
        current_storage_type = config_object.vm_object.getConfigObject(
        ).getConfig()['storage_type']
        if (current_storage_type is not config_object._getType()):
            if (number_of_disks):
                raise StorageTypesCannotBeMixedException(
                    'The VM (%s) is already configured with %s disks' %
                    (config_object.vm_object.getName(), current_storage_type))

            def updateStorageTypeConfig(config):
                config['storage_type'] = config_object._getType()
            config_object.vm_object.getConfigObject().updateConfig(
                updateStorageTypeConfig, 'Updated storage type for \'%s\' to \'%s\'' %
                (config_object.vm_object.getName(), config_object._getType()))

    @staticmethod
    def _createLogicalVolume(config_object, name, size, perform_on_nodes=False):
        """Creates a logical volume on the node/cluster"""
        from mcvirt.cluster.cluster import Cluster
        volume_group = config_object._getVolumeGroup()

        # Create command list
        command_args = ['/sbin/lvcreate', volume_group, '--name', name, '--size', '%sM' % size]
        try:
            # Create on local node
            System.runCommand(command_args)

            if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
                cluster = Cluster(config_object.vm_object.mcvirt_object)
                nodes = config_object.vm_object._getRemoteNodes()

                # Run on remote nodes
                cluster.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                         {'config': config_object._dumpConfig(),
                                          'name': name,
                                          'size': size},
                                         nodes=nodes)

        except MCVirtCommandException, e:
            # Remove any logical volumes that had been created if one of them fails
            Base._removeLogicalVolume(
                config_object,
                name,
                ignore_non_existent=True,
                perform_on_nodes=perform_on_nodes)
            raise MCVirtException("Error whilst creating disk logical volume:\n" + str(e))

    @staticmethod
    def _removeLogicalVolume(
            config_object,
            name,
            ignore_non_existent=False,
            perform_on_nodes=False):
        """Removes a logical volume from the node/cluster"""
        from mcvirt.cluster.cluster import Cluster

        # Create command arguments
        command_args = ['lvremove', '-f', config_object._getLogicalVolumePath(name)]
        try:
            # Determine if logical volume exists before attempting to remove it
            if (not (ignore_non_existent and
                     not Base._checkLogicalVolumeExists(config_object, name))):
                System.runCommand(command_args)

            if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
                cluster = Cluster(config_object.vm_object.mcvirt_object)
                nodes = config_object.vm_object._getRemoteNodes()

                # Run on remote nodes
                cluster.runRemoteCommand(
                    'virtual_machine-hard_drive-removeLogicalVolume', {
                        'config': config_object._dumpConfig(),
                        'name': name,
                        'ignore_non_existent': ignore_non_existent
                    },
                    nodes=nodes
                )
        except MCVirtCommandException, e:
            raise MCVirtException("Error whilst removing disk logical volume:\n" + str(e))

    @staticmethod
    def _getLogicalVolumeSize(config_object, name):
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
            config_object._getLogicalVolumePath(name))
        try:
            (_, command_output, _) = System.runCommand(command_args)
        except MCVirtCommandException, e:
            raise MCVirtException(
                "Error whilst obtaining the size of the logical volume:\n" +
                str(e))

        lv_size = command_output.strip().split('.')[0]
        return int(lv_size)

    @staticmethod
    def _zeroLogicalVolume(config_object, name, size, perform_on_nodes=False):
        """Blanks a logical volume by filling it with null data"""
        from mcvirt.cluster.cluster import Cluster

        # Obtain the path of the logical volume
        lv_path = config_object._getLogicalVolumePath(name)

        # Create command arguments
        command_args = ['dd', 'if=/dev/zero', 'of=%s' % lv_path, 'bs=1M', 'count=%s' % size]
        try:
            # Create logical volume on local node
            System.runCommand(command_args)

            if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
                cluster = Cluster(config_object.vm_object.mcvirt_object)
                nodes = config_object.vm_object._getRemoteNodes()

                # Create logical volume on remote nodes
                cluster.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                         {'config': config_object._dumpConfig(),
                                          'name': name, 'size': size},
                                         nodes=nodes)
        except MCVirtCommandException, e:
            raise MCVirtException("Error whilst zeroing logical volume:\n" + str(e))

    @staticmethod
    def _ensureLogicalVolumeExists(config_object, name):
        """Ensures that a logical volume exists, throwing an exception if it does not"""
        if (not Base._checkLogicalVolumeExists(config_object, name)):
            from mcvirt.cluster.cluster import Cluster
            raise LogicalVolumeDoesNotExistException(
                'Logical volume %s does not exist on %s' %
                (name, Cluster.getHostname()))

    @staticmethod
    def _checkLogicalVolumeExists(config_object, name):
        """Determines if a logical volume exists, returning 1 if present and 0 if not"""
        return os.path.lexists(config_object._getLogicalVolumePath(name))

    @staticmethod
    def _ensureLogicalVolumeActive(config_object, name):
        """Ensures that a logical volume is active"""
        if (not Base._checkLogicalVolumeActive(config_object, name)):
            from mcvirt.cluster.cluster import Cluster
            raise LogicalVolumeIsNotActive(
                'Logical volume %s is not active on %s' %
                (name, Cluster.getHostname()))

    @staticmethod
    def _checkLogicalVolumeActive(config_object, name):
        """Checks that a logical volume is active"""
        return os.path.exists(config_object._getLogicalVolumePath(name))

    @staticmethod
    def _activateLogicalVolume(config_object, name, perform_on_nodes=False):
        """Activates a logical volume on the node/cluster"""
        from mcvirt.cluster.cluster import Cluster

        # Obtain logical volume path
        lv_path = config_object._getLogicalVolumePath(name)

        # Create command arguments
        command_args = ['lvchange', '-a', 'y', '--yes', lv_path]
        try:
            # Run on the local node
            System.runCommand(command_args)

            if (perform_on_nodes and config_object.vm_object.mcvirt_object.initialiseNodes()):
                cluster = Cluster(config_object.vm_object.mcvirt_object)
                nodes = config_object.vm_object._getRemoteNodes()

                # Run on remote nodes
                cluster.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                         {'config': config_object._dumpConfig(),
                                          'name': name},
                                         nodes=nodes)
        except MCVirtCommandException, e:
            raise MCVirtException("Error whilst activating logical volume:\n" + str(e))

    def createBackupSnapshot(self):
        """Creates a snapshot of the logical volume for backing up and locks the VM"""
        from mcvirt.auth import Auth
        from mcvirt.virtual_machine.virtual_machine import LockStates
        # Ensure the user has permission to delete snapshot backups
        self.getConfigObject().vm_object.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.BACKUP_VM,
            self.getConfigObject().vm_object)

        # Ensure VM is registered locally
        self.getConfigObject().vm_object.ensureRegisteredLocally()

        # Obtain logical volume names/paths
        backup_volume_path = self.getConfigObject()._getLogicalVolumePath(
            self.getConfigObject()._getBackupLogicalVolume())
        snapshot_logical_volume = self.getConfigObject()._getBackupSnapshotLogicalVolume()

        # Determine if logical volume already exists
        if (Base._checkLogicalVolumeActive(self.getConfigObject(), snapshot_logical_volume)):
            raise BackupSnapshotAlreadyExistsException(
                'The backup snapshot for \'%s\' already exists: %s' %
                (backup_volume_path, snapshot_logical_volume)
            )

        # Lock the VM
        self.getConfigObject().vm_object.setLockState(LockStates.LOCKED)

        try:
            System.runCommand(['lvcreate', '--snapshot', backup_volume_path,
                               '--name', self.getConfigObject()._getBackupSnapshotLogicalVolume(),
                               '--size', self.getConfigObject().SNAPSHOT_SIZE])
            return self.getConfigObject()._getLogicalVolumePath(snapshot_logical_volume)
        except:
            self.getConfigObject().vm_object.setLockState(LockStates.UNLOCKED)
            raise

    def deleteBackupSnapshot(self):
        """Deletes the backup snapshot for the disk and unlocks the VM"""
        from mcvirt.auth import Auth
        from mcvirt.virtual_machine.virtual_machine import LockStates
        # Ensure the user has permission to delete snapshot backups
        self.getConfigObject().vm_object.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.BACKUP_VM,
            self.getConfigObject().vm_object
        )

        config = self.getConfigObject()
        # Ensure the snapshot logical volume exists
        if (not Base._checkLogicalVolumeActive(config, config._getBackupSnapshotLogicalVolume())):
            raise BackupSnapshotDoesNotExistException(
                'The backup snapshot for \'%s\' does not exist' %
                config._getLogicalVolumePath(config._getBackupLogicalVolume())
            )

        System.runCommand([
            'lvremove', '-f',
            self.getConfigObject()._getLogicalVolumePath(
                self.getConfigObject()._getBackupSnapshotLogicalVolume()
            )
        ])

        # Unlock the VM
        self.getConfigObject().vm_object.setLockState(LockStates.UNLOCKED)

    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        raise NotImplementedError

    def _checkExists(self):
        """Checks if the disk exists"""
        raise NotImplementedError

    def clone(self, destination_vm_object):
        """Clone a VM, using snapshotting, attaching it to the new VM object"""
        raise NotImplementedError

    @staticmethod
    def create(vm_object, size):
        """Creates a new disk image, attaches the disk to the VM and records the disk
        in the VM configuration"""
        raise NotImplementedError

    def activateDisk(self):
        """Activates the storage volume"""
        raise NotImplementedError

    def deactivateDisk(self):
        """Deactivates the storage volume"""
        raise NotImplementedError

    def offlineMigrateCheckState(self, destination_node):
        """Determines if the disk is in a state to allow the attached VM
           to be migrated to another node"""
        raise NotImplementedError

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        raise NotImplementedError

    def move(self, destination_node, source_node):
        """Moves the storage to another node in the cluster"""
        raise NotImplementedError

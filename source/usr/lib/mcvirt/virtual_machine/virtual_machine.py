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
import re
import os
import shutil
from texttable import Texttable
from enum import Enum
import Pyro4

from mcvirt.mcvirt import MCVirt, MCVirtException
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.virtual_machine.disk_drive import DiskDrive
from mcvirt.virtual_machine.network_adapter import NetworkAdapter
from mcvirt.virtual_machine.virtual_machine_config import VirtualMachineConfig
from mcvirt.auth.auth import Auth
from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from mcvirt.node.network import Network
from mcvirt.virtual_machine.hard_drive.config.base import Base as HardDriveConfigBase


class UnkownException(MCVirtException):
    """An unkown error occurred whislt performing a LibVirt action"""
    pass


class MigrationFailureExcpetion(MCVirtException):
    """A Libvirt Exception occurred whilst performing a migration"""
    pass


class InvalidVirtualMachineNameException(MCVirtException):
    """VM is being created with an invalid name"""
    pass


class VmAlreadyExistsException(MCVirtException):
    """VM is being created with a duplicate name"""
    pass


class VmDirectoryAlreadyExistsException(MCVirtException):
    """Directory for a VM already exists"""
    pass


class VmAlreadyStoppedException(MCVirtException):
    """VM is already stopped when attempting to stop it"""
    pass


class VmAlreadyStartedException(MCVirtException):
    """VM is already started when attempting to start it"""
    pass


class VmAlreadyRegisteredException(MCVirtException):
    """VM is already registered on a node"""
    pass


class VmRegisteredElsewhereException(MCVirtException):
    """Attempt to perform an action on a VM registered on another node"""
    pass


class VmRunningException(MCVirtException):
    """An offline migration can only be performed on a powered off VM"""
    pass


class VmStoppedException(MCVirtException):
    """An online migraiton can only be performed on a powered on VM"""


class UnsuitableNodeException(MCVirtException):
    """The node is unsuitable to run the VM"""
    pass


class VmNotRegistered(MCVirtException):
    """The virtual machine is not currently registered on a node"""
    pass


class CannotStartClonedVmException(MCVirtException):
    """Cloned VMs cannot be started"""
    pass


class CannotCloneDrbdBasedVmsException(MCVirtException):
    """Cannot clone DRBD-based VMs"""
    pass


class CannotDeleteClonedVmException(MCVirtException):
    """Cannot delete a cloned VM"""
    pass


class VirtualMachineLockException(MCVirtException):
    """Lock cannot be set to the current lock state"""
    pass


class LockStates(Enum):
    """Library of virtual machine lock states"""
    UNLOCKED = 0
    LOCKED = 1


class PowerStates(Enum):
    """Library of virtual machine power states"""
    STOPPED = 0
    RUNNING = 1
    UNKNOWN = 2


class VirtualMachine(object):
    """Provides operations to manage a LibVirt virtual machine"""

    def __init__(self, mcvirt_object, name):
        """Sets member variables and obtains LibVirt domain object"""
        self.name = name
        self.mcvirt_object = mcvirt_object

        # Ensure that the connection is alive
        if (not self.mcvirt_object.getLibvirtConnection().isAlive()):
            raise UnkownException('Error: LibVirt connection not alive')

        # Check that the domain exists
        if (not VirtualMachine._checkExists(self.mcvirt_object, self.name)):
            raise MCVirtException('Error: Virtual Machine does not exist: %s' % self.name)

    def getConfigObject(self):
        """Returns the configuration object for the VM"""
        return VirtualMachineConfig(self)

    @Pyro4.expose()
    def getName(self):
        """Returns the name of the VM"""
        return self.name

    def _getLibvirtDomainObject(self):
        """Looks up LibVirt domain object, based on VM name,
        and return object"""
        # Get the domain object.
        return self.mcvirt_object.getLibvirtConnection().lookupByName(self.name)

    @Pyro4.expose()
    def stop(self):
        """Stops the VM"""
        # Check the user has permission to start/stop VMs
        self.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.CHANGE_VM_POWER_STATE,
            self)

        # Determine if VM is registered on the local machine
        if self.isRegisteredLocally():
            # Determine if VM is running
            if (self.getPowerState() is PowerStates.RUNNING):
                try:
                    # Stop the VM
                    self._getLibvirtDomainObject().destroy()
                except Exception, e:
                    raise UnkownException('Failed to stop VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('The VM is already shutdown')
        elif self.mcvirt_object.initialiseNodes():
            from mcvirt.cluster.cluster import Cluster
            cluster_object = Cluster(self.mcvirt_object)
            remote = cluster_object.getRemoteNode(self.getNode())
            remote.runRemoteCommand('virtual_machine-stop',
                                    {'vm_name': self.getName()})

        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    def start(self, iso_object=None):
        """Starts the VM"""
        # Check the user has permission to start/stop VMs
        self.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.CHANGE_VM_POWER_STATE,
            self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        if self.isRegisteredLocally():
            # Ensure VM hasn't been cloned
            if (self.getCloneChildren()):
                raise CannotStartClonedVmException('Cloned VMs cannot be started')

            # Determine if VM is stopped
            if (self.getPowerState() is PowerStates.RUNNING):
                raise VmAlreadyStartedException('The VM is already running')

            for disk_object in self.getDiskObjects():
                disk_object.activateDisk()

            disk_drive_object = DiskDrive(self)
            if (iso_object):
                # If an ISO has been specified, attach it to the VM before booting
                # and adjust boot order to boot from ISO first
                disk_drive_object.attachISO(iso_object)
                self.setBootOrder(['cdrom', 'hd'])
            else:
                # If not ISO was specified, remove any attached ISOs and change boot order
                # to boot from HDD
                disk_drive_object.removeISO()
                self.setBootOrder(['hd'])

            # Start the VM
            try:
                self._getLibvirtDomainObject().create()
            except Exception, e:
                raise UnkownException('Failed to start VM: %s' % e)

        elif self.mcvirt_object.initialiseNodes():
            from mcvirt.cluster.cluster import Cluster
            cluster_object = Cluster(self.mcvirt_object)
            remote = cluster_object.getRemoteNode(self.getNode())
            if (iso_object):
                iso_name = iso_object.getName()
            else:
                iso_name = None
            remote.runRemoteCommand('virtual_machine-start',
                                    {'vm_name': self.getName(),
                                     'iso': iso_name})

        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    def reset(self):
        """Resets the VM"""
        # Check the user has permission to start/stop VMs
        self.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.CHANGE_VM_POWER_STATE,
            self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        if self.isRegisteredLocally():
            # Determine if VM is running
            if (self.getPowerState() is PowerStates.RUNNING):
                try:
                    # Reset the VM
                    self._getLibvirtDomainObject().reset()
                except Exception, e:
                    raise UnkownException('Failed to reset VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('Cannot reset a stopped VM')
        elif self.mcvirt_object.initialiseNodes():
            from mcvirt.cluster.cluster import Cluster
            cluster_object = Cluster(self.mcvirt_object)
            remote = cluster_object.getRemoteNode(self.getNode())
            remote.runRemoteCommand('virtual_machine-reset',
                                    {'vm_name': self.getName()})

        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    def getPowerState(self, enum=False):
        """Returns the power state of the VM in the form of a PowerStates enum"""
        if (self.isRegisteredLocally()):
            if (self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING):
                if self._pyroDaemon and not enum:
                    return PowerStates.RUNNING.value
                return PowerStates.RUNNING
            else:
                if self._pyroDaemon and not enum:
                    return PowerStates.STOPPED.value
                return PowerStates.STOPPED

        elif (self.isRegisteredRemotely() and
              not self.getNode() in self.mcvirt_object.failed_nodes):
            from mcvirt.cluster.cluster import Cluster
            cluster_object = Cluster(self.mcvirt_object)
            remote = cluster_object.getRemoteNode(self.getNode())
            return PowerStates(remote.runRemoteCommand('virtual_machine-getPowerState',
                                                       {'vm_name': self.getName()}))
        else:
            return PowerStates.UNKNOWN

    def getInfo(self):
        """Gets information about the current VM"""
        warnings = ''

        if (not self.isRegistered()):
            warnings += 'Warning: Some details are not available' + \
                        " as the VM is not registered on a node\n"

        if ((self.isRegisteredRemotely() and
             not self.getNode() in self.mcvirt_object.failed_nodes)):

            from mcvirt.cluster.cluster import Cluster
            cluster_instance = Cluster(self.mcvirt_object)
            remote_object = cluster_instance.getRemoteNode(self.getNode())
            return remote_object.runRemoteCommand('virtual_machine-getInfo',
                                                  {'vm_name': self.getName()})

        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.add_row(('Name', self.getName()))
        table.add_row(('CPU Cores', self.getCPU()))
        table.add_row(('Memory Allocation', str(int(self.getRAM()) / 1024) + 'MB'))
        table.add_row(('State', self.getPowerState().name))
        table.add_row(('Node', self.getNode()))
        table.add_row(('Available Nodes', ', '.join(self.getAvailableNodes())))

        # Display clone children, if they exist
        clone_children = self.getCloneChildren()
        if (len(clone_children)):
            table.add_row(('Clone Children', ','.join(clone_children)))

        # Display clone parent, if it exists
        clone_parent = self.getCloneParent()
        if (clone_parent):
            table.add_row(('Clone Parent', clone_parent))

        # The ISO can only be displayed if the VM is on the local node
        if (self.isRegisteredLocally()):
            # Display the path of the attached ISO (if present)
            disk_object = DiskDrive(self)
            iso_object = disk_object.getCurrentDisk()
            if (iso_object):
                disk_name = iso_object.getName()
            else:
                disk_name = None
        else:
            disk_name = 'Unavailable'

        if (disk_name):
            table.add_row(('ISO location', disk_name))

        # Get info for each disk
        disk_objects = self.getDiskObjects()
        if (len(disk_objects)):
            table.add_row(('-- Disk ID --', '-- Disk Size --'))
            for disk_object in disk_objects:
                table.add_row(
                    (str(disk_object.getConfigObject().getId()),
                     str(int(disk_object.getSize()) / 1000) + 'GB')
                )
        else:
            warnings += "No hard disks present on machine\n"

        # Create info table for network adapters
        network_adapters = self.getNetworkObjects()
        if (len(network_adapters) != 0):
            table.add_row(('-- MAC Address --', '-- Network --'))
            for network_adapter in network_adapters:
                table.add_row(
                    (network_adapter.getMacAddress(),
                     network_adapter.getConnectedNetwork()))
        else:
            warnings += "No network adapters present on machine\n"

        # Get information about the permissions for the VM
        table.add_row(('-- Group --', '-- Users --'))
        for permission_group in self.mcvirt_object.getAuthObject().getPermissionGroups():
            users = self.mcvirt_object.getAuthObject().getUsersInPermissionGroup(
                permission_group,
                self)
            users_string = ','.join(users)
            table.add_row((permission_group, users_string))

        return table.draw() + "\n" + warnings

    def delete(self, remove_data=False, local_only=False):
        """Delete the VM - removing it from LibVirt and from the filesystem"""
        from mcvirt.cluster.cluster import Cluster
        # Check the user has permission to modify VMs or
        # that the user is the owner of the VM and the VM is a clone
        if not (
            self.mcvirt_object.getAuthObject().checkPermission(
                Auth.PERMISSIONS.MODIFY_VM,
                self) or (
                self.getCloneParent() and self.mcvirt_object.getAuthObject().checkPermission(
                Auth.PERMISSIONS.DELETE_CLONE,
                self))):
            raise MCVirtException(
                'User does not have the required permission - ' +
                'User must have MODIFY_VM permission or be the owner of the cloned VM')

        # Ensure the VM is not being removed from a machine that the VM is not being run on
        if ((self.isRegisteredRemotely() and self.mcvirt_object.initialiseNodes() and
             not local_only)):
            remote_node = self.getConfigObject().getConfig()['node']
            raise VmRegisteredElsewhereException(
                'The VM \'%s\' is registered on the remote node: %s' %
                (self.getName(), remote_node))

        # Determine if VM is running
        if (self.isRegisteredLocally() and self._getLibvirtDomainObject().state()
                [0] == libvirt.VIR_DOMAIN_RUNNING):
            raise MCVirtException('Error: Can\'t delete running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure that VM has not been cloned
        if (self.getCloneChildren()):
            raise CannotDeleteClonedVmException('Can\'t delete cloned VM')

        # If 'remove_data' has been passed as True, delete disks associated
        # with VM
        if (remove_data and Cluster.getHostname() in self.getAvailableNodes()):
            for disk_object in self.getDiskObjects():
                disk_object.delete()

        # 'Undefine' object from LibVirt
        if (self.isRegisteredLocally()):
            try:
                self._getLibvirtDomainObject().undefine()
            except:
                raise MCVirtException('Failed to delete VM from libvirt')

        # If VM is a clone of another VM, remove it from the configuration
        # of the parent
        if (self.getCloneParent()):
            def removeCloneChildConfig(vm_config):
                """Remove a given child VM from a parent VM configuration"""
                vm_config['clone_children'].remove(self.getName())

            parent_vm_object = VirtualMachine(self.mcvirt_object, self.getCloneParent())
            parent_vm_object.getConfigObject().updateConfig(
                removeCloneChildConfig, 'Removed clone child \'%s\' from \'%s\'' %
                (self.getName(), self.getCloneParent()))

        # If 'remove_data' has been passed as True, delete directory
        # from VM storage
        if (remove_data):
            # Remove VM configuration file
            self.getConfigObject().gitRemove('VM \'%s\' has been removed' % self.name)
            shutil.rmtree(VirtualMachine.getVMDir(self.name))

        # Remove VM from MCVirt configuration
        def updateMCVirtConfig(config):
            config['virtual_machines'].remove(self.name)
        MCVirtConfig().updateConfig(
            updateMCVirtConfig,
            'Removed VM \'%s\' from global MCVirt config' %
            self.name)

        if (self.mcvirt_object.initialiseNodes() and not local_only):
            cluster_object = Cluster(self.mcvirt_object)
            cluster_object.runRemoteCommand('virtual_machine-delete',
                                            {'vm_name': self.name,
                                             'remove_data': remove_data})

    def getRAM(self):
        """Returns the amount of memory attached the VM"""
        return self.getConfigObject().getConfig()['memory_allocation']

    def updateRAM(self, memory_allocation):
        """Updates the amount of RAM allocated to a VM"""
        # Check the user has permission to modify VMs
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MODIFY_VM, self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure the VM is registered locally
        self.ensureRegisteredLocally()

        def updateXML(domain_xml):
            # Update RAM allocation and unit measurement
            domain_xml.find('./memory').text = str(memory_allocation)
            domain_xml.find('./memory').set('unit', 'KiB')
            domain_xml.find('./currentMemory').text = str(memory_allocation)
            domain_xml.find('./currentMemory').set('unit', 'KiB')

        self.editConfig(updateXML)

        # Update the MCVirt configuration
        self.updateConfig(['memory_allocation'], str(memory_allocation),
                          'RAM allocation has been changed to %s' % memory_allocation)

    def getCPU(self):
        """Returns the number of CPU cores attached to the VM"""
        return self.getConfigObject().getConfig()['cpu_cores']

    def updateCPU(self, cpu_count):
        """Updates the number of CPU cores attached to a VM"""
        # Check the user has permission to modify VMs
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MODIFY_VM, self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Determine if VM is registered on the local machine
        self.ensureRegisteredLocally()

        def updateXML(domain_xml):
            # Update RAM allocation and unit measurement
            domain_xml.find('./vcpu').text = str(cpu_count)
        self.editConfig(updateXML)

        # Update the MCVirt configuration
        self.updateConfig(['cpu_cores'], str(cpu_count), 'CPU count has been changed to %s' %
                                                         cpu_count)

    def getNetworkObjects(self):
        """Returns an array of network interface objects for each of the
        interfaces attached to the VM"""
        interfaces = []
        for mac_address in self.getConfigObject().getConfig()['network_interfaces'].keys():
            interface_object = NetworkAdapter(mac_address, self)
            interfaces.append(interface_object)
        return interfaces

    def getDiskObjects(self):
        """Returns an array of disk objects for the disks attached to the VM"""
        disks = self.getConfigObject().getConfig()['hard_disks']
        disk_objects = []
        for disk_id in disks:
            disk_objects.append(HardDriveFactory.getObject(self, disk_id))
        return disk_objects

    def updateConfig(self, attribute_path, value, reason):
        """Updates a VM configuration attribute and
           replicates change across all nodes"""
        # Update the local configuration
        def updateLocalConfig(config):
            config_level = config
            for attribute in attribute_path[:-1]:
                config_level = config_level[attribute]
            config_level[attribute_path[-1]] = value

        self.getConfigObject().updateConfig(updateLocalConfig, reason)

        if (self.mcvirt_object.initialise_nodes):
            from mcvirt.cluster.cluster import Cluster
            cluster_instance = Cluster(self.mcvirt_object)
            cluster_instance.runRemoteCommand('virtual_machine-virtual_machine-updateConfig',
                                              {'vm_name': self.getName(),
                                               'attribute_path': attribute_path, 'value': value,
                                               'reason': reason})

    @staticmethod
    def _checkExists(mcvirt_instance, name):
        """Check if a domain exists"""
        from factory import Factory
        factory = Factory(mcvirt_instance)
        return (name in factory.getAllVmNames())

    @staticmethod
    def getVMDir(name):
        """Returns the storage directory for a given VM"""
        return MCVirt.BASE_VM_STORAGE_DIR + '/' + name

    def getLibvirtConfig(self):
        """Returns an XML object of the libvirt configuration
        for the domain"""
        domain_flags = (libvirt.VIR_DOMAIN_XML_INACTIVE + libvirt.VIR_DOMAIN_XML_SECURE)
        domain_xml = ET.fromstring(self._getLibvirtDomainObject().XMLDesc(domain_flags))
        return domain_xml

    def editConfig(self, callback_function):
        """Provides an interface for updating the libvirt configuration, by obtaining
        the configuration, performing a callback function to perform changes on the configuration
        and pushing the configuration back into LibVirt"""
        # Obtain VM XML
        domain_flags = (libvirt.VIR_DOMAIN_XML_INACTIVE + libvirt.VIR_DOMAIN_XML_SECURE)
        domain_xml = ET.fromstring(self._getLibvirtDomainObject().XMLDesc(domain_flags))

        # Perform callback function to make changes to the XML
        callback_function(domain_xml)

        # Push XML changes back to LibVirt
        domain_xml_string = ET.tostring(domain_xml, encoding='utf8', method='xml')

        try:
            self.mcvirt_object.getLibvirtConnection().defineXML(domain_xml_string)
        except:
            raise MCVirtException('Error: An error occurred whilst updating the VM')

    def getCloneParent(self):
        """Determines if a VM is a clone of another VM"""
        return self.getConfigObject().getConfig()['clone_parent']

    def getCloneChildren(self):
        """Returns the VMs that have been cloned from the VM"""
        return self.getConfigObject().getConfig()['clone_children']

    def offlineMigrate(
            self,
            destination_node_name,
            start_after_migration=False,
            wait_for_vm_shutdown=False):
        """Performs an offline migration of a VM to another node in the cluster"""
        import time
        from mcvirt.cluster.cluster import Cluster
        # Ensure user has permission to migrate VM
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MIGRATE_VM, self)

        # Ensure the VM is locally registered
        self.ensureRegisteredLocally()

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is using a DRBD storage type
        self._preMigrationChecks(destination_node_name)

        # Check if VM is running
        while (self.getPowerState() is PowerStates.RUNNING):
            # Unless the user has specified to wait for the VM to shutdown, throw an exception
            # if the VM is running
            if (not wait_for_vm_shutdown):
                raise VmRunningException(
                    'An offline migration can only be performed on a powered off VM. '
                    'Use --wait-for-shutdown to wait until the '
                    'VM is powered off before migrating.'
                )

            # Wait for 5 seconds before checking the VM state again
            time.sleep(5)

        # Unregister the VM on the local node
        self.unregister()

        # Register on remote node
        cluster_instance = Cluster(self.mcvirt_object)
        remote_object = cluster_instance.getRemoteNode(destination_node_name)
        remote_object.runRemoteCommand('virtual_machine-register',
                                       {'vm_name': self.getName()})

        # Set the node of the VM
        self._setNode(destination_node_name)

        # If the user has specified to start the VM after migration, start it on
        # the remote node
        if (start_after_migration):
            remote_object.runRemoteCommand('virtual_machine-start',
                                           {'vm_name': self.getName()})

    def onlineMigrate(self, destination_node_name):
        """Performs an online migration of a VM to another node in the cluster"""
        from mcvirt.cluster.cluster import Cluster
        from factory import Factory
        factory = Factory(self.mcvirt_object)

        # Ensure user has permission to migrate VM
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MIGRATE_VM, self)

        # Ensure VM is registered locally and unlocked
        self.ensureRegisteredLocally()
        self.ensureUnlocked()

        # Perform pre-migration checks
        self._preMigrationChecks(destination_node_name)

        # Perform online-migration-specific checks
        self._preOnlineMigrationChecks(destination_node_name)

        # Obtain cluster instance
        cluster_instance = Cluster(self.mcvirt_object)

        # Begin pre-migration tasks
        try:
            # Obtain node object for destination node
            destination_node = cluster_instance.getRemoteNode(destination_node_name)

            # Obtain libvirt connection to destination node
            destination_libvirt_connection = self.mcvirt_object.getRemoteLibvirtConnection(
                destination_node
            )

            # Clear the VM node configuration
            self._setNode(None)

            # Perform pre-migration tasks on disk objects
            for disk_object in self.getDiskObjects():
                disk_object.preOnlineMigration(destination_node)

            # Build migration flags
            migration_flags = (
                # Perform a live migration
                libvirt.VIR_MIGRATE_LIVE |
                # The set destination domain as persistent
                libvirt.VIR_MIGRATE_PERSIST_DEST |
                # Undefine the domain on the source node
                libvirt.VIR_MIGRATE_UNDEFINE_SOURCE |
                # Abort migration on I/O errors
                libvirt.VIR_MIGRATE_ABORT_ON_ERROR
            )

            # Perform migration
            libvirt_domain_object = self._getLibvirtDomainObject()
            status = libvirt_domain_object.migrate3(
                destination_libvirt_connection,
                params={},
                flags=migration_flags
            )

            if (not status):
                raise MigrationFailureExcpetion('Libvirt migration failed')

            # Perform post steps on hard disks and check disks
            for disk_object in self.getDiskObjects():
                disk_object.postOnlineMigration()
                disk_object._checkDrbdStatus()

            # Set the VM node to the destination node node
            self._setNode(destination_node_name)

        except Exception as e:
            # Determine which node the VM is present on
            vm_registration_found = False

            # Wait 10 seconds before performing the tear-down, as DRBD
            # will hold the block device open for a short period
            import time
            time.sleep(10)

            if (self.getName() in factory.getAllVms(node=Cluster.getHostname())):
                # VM is registered on the local node.
                vm_registration_found = True

                # Set DRBD on remote node to secondary
                for disk_object in self.getDiskObjects():
                    cluster_instance.runRemoteCommand(
                        'virtual_machine-hard_drive-drbd-drbdSetSecondary',
                        {'vm_name': self.getName(),
                         'disk_id': disk_object.getConfigObject().getId()},
                        nodes=[destination_node_name])

                # Re-register VM as being registered on the local node
                self._setNode(Cluster.getHostname())

            if (self.getName() in factory.getAllVms(node=destination_node_name)):
                # Otherwise, if VM is registered on remote node, set the
                # local DRBD state to secondary
                vm_registration_found = True
                for disk_object in self.getDiskObjects():
                    import time
                    time.sleep(10)
                    disk_object._drbdSetSecondary()

                # Register VM as being registered on the local node
                self._setNode(destination_node_name)

            # Reset disks
            for disk_object in self.getDiskObjects():
                # Reset dual-primary configuration
                disk_object._setTwoPrimariesConfig(allow=False)

                # Mark hard drives as being out-of-sync
                disk_object.setSyncState(False)

            raise e

        # Perform post migration checks
        # Ensure VM is no longer registered with libvirt on the local node
        if (self.getName() in factory.getAllVms(node=Cluster.getHostname())):
            raise VmAlreadyRegisteredException(
                'The VM is unexpectedly registered with libvirt on the local node: %s' %
                self.getName()
            )

        # Ensure VM is registered on the remote libvirt instance
        if (self.getName() not in factory.getAllVms(node=destination_node_name)):
            raise VmNotRegistered(
                'The VM is unexpectedly not registered with libvirt on the destination node: %s' %
                destination_node_name
            )

        # Ensure VM is running on the remote node
        if (self.getPowerState() is not PowerStates.RUNNING):
            raise VmStoppedException('VM is in unexpected %s power state after migration' %
                                     self.getPowerState())

    def _preMigrationChecks(self, destination_node_name):
        """Performs checks on the state of the VM to determine if is it suitable to
           be migrated"""
        # Ensure node is in the available nodes that the VM can be run on
        if (destination_node_name not in self.getAvailableNodes()):
            raise UnsuitableNodeException(
                'The remote node %s is not marked as being able to host the VM %s' %
                (destination_node_name, self.getName()))

        # Obtain remote object for destination node
        from mcvirt.cluster.cluster import Cluster
        cluster_instance = Cluster(self.mcvirt_object)
        remote_node = cluster_instance.getRemoteNode(destination_node_name)

        # Checks the DRBD state of the disks and ensure that they are
        # in a suitable state to be migrated
        for disk_object in self.getDiskObjects():
            disk_object.preMigrationChecks()

        # Check the remote node to ensure that the networks, that the VM is connected to,
        # exist on the remote node
        for network_object in self.getNetworkObjects():
            connected_network = network_object.getConnectedNetwork()
            exists_on_remote_node = remote_node.runRemoteCommand(
                'node-network-checkExists', {'network_name': connected_network})
            if (not exists_on_remote_node):
                raise UnsuitableNodeException(
                    'The network %s does not exist on the remote node: %s' %
                    (connected_network, destination_node_name)
                )

    def _preOnlineMigrationChecks(self, destination_node_name):
        """Perform online-migration-specific pre-migration checks"""
        # Ensure any attached ISOs exist on the destination node
        disk_drive_object = DiskDrive(self)
        disk_drive_object.preOnlineMigrationChecks(destination_node_name)

        # Ensure VM is powered on
        if (self.getPowerState() is not PowerStates.RUNNING):
            raise VmStoppedException(
                'An online migration can only be performed on a running VM: %s' %
                self.getName()
            )

    def getStorageType(self):
        """Returns the storage type of the VM"""
        return self.getConfigObject().getConfig()['storage_type']

    def clone(self, mcvirt_instance, clone_vm_name):
        """Clones a VM, creating an identical machine, using
           LVM snapshotting to duplicate the Hard disk. DRBD is not
           currently supported"""
        # Check the user has permission to create VMs
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.CLONE_VM, self)

        # Ensure the storage type for the VM is not DRBD, as DRBD-based VMs cannot be cloned
        if (self.getStorageType() == 'DRBD'):
            raise CannotCloneDrbdBasedVmsException(
                'Cannot clone VM that uses DRBD-based storage: %s' %
                self.getName()
            )

        # Determine if VM is running
        if (self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING):
            raise MCVirtException('Can\'t clone running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure new VM name doesn't already exist
        VirtualMachine._checkExists(self.mcvirt_object, clone_vm_name)

        # Ensure VM is not a clone, as cloning a cloned VM will cause issues
        if (self.getCloneParent()):
            raise MCVirtException('Cannot clone from a clone VM')

        # Create new VM for clone, without hard disks
        network_objects = self.getNetworkObjects()
        networks = []
        for network_object in network_objects:
            networks.append(network_object.getConnectedNetwork())
        new_vm_object = VirtualMachine.create(mcvirt_instance, clone_vm_name, self.getCPU(),
                                              self.getRAM(), [], networks, auth_check=False,
                                              available_nodes=self.getAvailableNodes(),
                                              node=self.getNode())

        # Mark VM as being a clone and mark parent as being a clone
        def setCloneParent(vm_config):
            vm_config['clone_parent'] = self.getName()

        new_vm_object.getConfigObject().updateConfig(
            setCloneParent,
            'Set VM clone parent after initial clone')

        def setCloneChild(vm_config):
            vm_config['clone_children'].append(new_vm_object.getName())

        self.getConfigObject().updateConfig(
            setCloneChild,
            'Added new clone \'%s\' to VM configuration' %
            self.getName())

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self.mcvirt_object.getAuthObject().copyPermissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.getDiskObjects()
        for disk_object in disk_objects:
            disk_object.clone(new_vm_object)

        return new_vm_object

    def duplicate(self, mcvirt_instance, duplicate_vm_name):
        """Duplicates a VM, creating an identical machine, making a
           copy of the storage"""
        # Check the user has permission to create VMs
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.DUPLICATE_VM, self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Determine if VM is running
        if (self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING):
            raise MCVirtException('Can\'t duplicate running VM')

        # Ensure new VM name doesn't already exist
        VirtualMachine._checkExists(self.mcvirt_object, duplicate_vm_name)

        # Create new VM for clone, without hard disks
        network_objects = self.getNetworkObjects()
        networks = []
        for network_object in network_objects:
            networks.append(network_object.getConnectedNetwork())
        new_vm_object = VirtualMachine.create(mcvirt_instance, duplicate_vm_name, self.getCPU(),
                                              self.getRAM(), [], networks, auth_check=False,
                                              available_nodes=self.getAvailableNodes(),
                                              node=self.getNode())

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self.mcvirt_object.getAuthObject().copyPermissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.getDiskObjects()
        for disk_object in disk_objects:
            disk_object.duplicate(new_vm_object)

        return new_vm_object

    def move(self, destination_node, source_node=None):
        """Move a VM from one node to another"""
        # Ensure user has the ability to move VMs
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MOVE_VM, self)

        from mcvirt.cluster.cluster import Cluster
        cluster_instance = Cluster(self.mcvirt_object)

        # Ensure that the VM is registered on the local node
        self.ensureRegisteredLocally()

        # Set the source node as the local host, if the VM is VM
        # uses local-based storage
        if (self.getStorageType() == 'Local'):
            if (source_node is None):
                source_node = Cluster.getHostname()

            # If migrating a local VM, since the only instance of the storage will be moved,
            # ensure that the VM is stopped
            if (self.getPowerState is not PowerStates.STOPPED):
                raise VmRunningException('VM must be stopped before performing a move')

        # Perform checks on source and remote nodes
        if (destination_node == source_node):
            raise UnsuitableNodeException('Source node and destination node must' +
                                          ' be different nodes')
        if (not cluster_instance.checkNodeExists(source_node)):
            raise UnsuitableNodeException('Source node does not exist: %s' % source_node)
        if (not cluster_instance.checkNodeExists(destination_node)):
            raise UnsuitableNodeException('Destination node does not exist')
        if (destination_node == Cluster.getHostname()):
            raise UnsuitableNodeException('VM must be migrated to a remote node')
        if (destination_node in self.getAvailableNodes()):
            raise UnsuitableNodeException('Destination node is already' +
                                          ' an available node for the VM')
        if (source_node not in self.getAvailableNodes()):
            raise UnsuitableNodeException('Source node is not configured for the VM')

        # Ensure that, if the VM is DRBD-backed, that the local node is not the source
        if ((self.getStorageType() == 'DRBD' and
             source_node == Cluster.getHostname())):
            raise UnsuitableNodeException('DRBD-backed VMs must be moved on the node' +
                                          ' that will remain attached to the VM')

        # Remove the destination node from the list of available nodes for the VM and
        # add the remote node as an available node
        available_nodes = self.getAvailableNodes()
        available_nodes.remove(source_node)
        available_nodes.append(destination_node)
        self.updateConfig(['available_nodes'], available_nodes,
                          'Moved VM \'%s\' from node \'%s\' to node \'%s\'' %
                          (self.getName(), source_node, destination_node))

        # Move each of the attached disks to the remote node
        for disk_object in self.getDiskObjects():
            disk_object.move(source_node=source_node, destination_node=destination_node)

        # If the VM is a Local VM, unregister it from the local node
        if (self.getStorageType() == 'Local'):
            self.unregister()

        # If the VM is a local VM, register it on the remote node
        if (self.getStorageType() == 'Local'):
            remote_node = cluster_instance.getRemoteNode(destination_node)
            remote_node.runRemoteCommand('virtual_machine-register',
                                         {'vm_name': self.getName()})

    @staticmethod
    def create(mcvirt_instance, name, cpu_cores, memory_allocation, hard_drives=[],
               network_interfaces=[], node=None, available_nodes=[], storage_type=None,
               auth_check=True, hard_drive_driver=None):
        """Creates a VM and returns the virtual_machine object for it"""
        from mcvirt.cluster.cluster import (Cluster, ClusterNotInitialisedException,
                                            NodeDoesNotExistException)

        if (auth_check):
            mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.CREATE_VM)

        # Validate the VM name
        valid_name_re = re.compile(r'[^a-z^0-9^A-Z-]').search
        if (bool(valid_name_re(name))):
            raise InvalidVirtualMachineNameException(
                'Error: Invalid VM Name - VM Name can only contain 0-9 a-Z and dashes')

        # Ensure the cluster has not been ignored, as VMs cannot be created with MCVirt running
        # in this state
        if (mcvirt_instance.ignore_failed_nodes):
            raise ClusterNotInitialisedException('VM cannot be created whilst the cluster' +
                                                 ' is not initialised')

        # Determine if VM already exists
        if (VirtualMachine._checkExists(mcvirt_instance, name)):
            raise VmAlreadyExistsException('Error: VM already exists')

        # If a node has not been specified, assume the local node
        if (node is None):
            node = Cluster.getHostname()

        # If DRBD has been chosen as a storage type, ensure it is enabled on the node
        from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode
        if (storage_type == 'DRBD' and not NodeDRBD.isEnabled()):
            raise DRBDNotEnabledOnNode('DRBD is not enabled on this node')

        # Create directory for VM on the local and remote nodes
        if (os.path.exists(VirtualMachine.getVMDir(name))):
            raise VmDirectoryAlreadyExistsException('Error: VM directory already exists')

        # If available nodes has not been passed, assume the local machine is the only
        # available node if local storage is being used. Use the machines in the cluster
        # if DRBD is being used
        cluster_object = Cluster(mcvirt_instance)
        all_nodes = cluster_object.getNodes()
        all_nodes.append(Cluster.getHostname())
        if (len(available_nodes) == 0):
            if (storage_type == 'DRBD' and mcvirt_instance.initialiseNodes()):
                # If the available nodes are not specified, use the
                # nodes in the cluster
                available_nodes = all_nodes
            else:
                # For local VMs, only use the local node as the available nodes
                available_nodes = [Cluster.getHostname()]

        # If there are more than the maximum number of DRBD machines in the cluster,
        # add an option that forces the user to specify the nodes for the DRBD VM
        # to be added to
        if (storage_type == 'DRBD' and len(available_nodes) != NodeDRBD.CLUSTER_SIZE):
            raise MCVirtException('Exactly two nodes must be specified')

        for check_node in available_nodes:
            if (check_node not in all_nodes):
                raise NodeDoesNotExistException('Node \'%s\' does not exist' % check_node)

        if (Cluster.getHostname() not in available_nodes and mcvirt_instance.initialiseNodes()):
            raise MCVirtException('One of the nodes must be the local node')

        # Create directory for VM
        os.makedirs(VirtualMachine.getVMDir(name))

        # Add VM to MCVirt configuration
        def updateMCVirtConfig(config):
            config['virtual_machines'].append(name)
        MCVirtConfig().updateConfig(
            updateMCVirtConfig,
            'Adding new VM \'%s\' to global MCVirt configuration' %
            name)

        # Create VM configuration file
        VirtualMachineConfig.create(name, available_nodes, cpu_cores, memory_allocation)

        # Add VM to remote nodes
        if (mcvirt_instance.initialiseNodes()):
            cluster_object.runRemoteCommand('virtual_machine-create',
                                            {'vm_name': name,
                                             'memory_allocation': memory_allocation,
                                             'cpu_cores': cpu_cores,
                                             'node': node,
                                             'available_nodes': available_nodes})

        # Obtain an object for the new VM, to use to create disks/network interfaces
        vm_object = VirtualMachine(mcvirt_instance, name)
        vm_object.getConfigObject().gitAdd('Created VM \'%s\'' % vm_object.getName())

        if (node == Cluster.getHostname()):
            # Register VM with LibVirt. If MCVirt has not been initialised on this node,
            # do not set the node in the VM configuration, as the change can't be
            # replicated to remote nodes
            vm_object.register(set_node=mcvirt_instance.initialiseNodes())
        elif (mcvirt_instance.initialiseNodes()):
            # If MCVirt has been initialised on this node and the local machine is
            # not the node that the VM will be registered on, set the node on the VM
            vm_object._setNode(node)

        # If a storage type has not been specified, assume the default
        if (storage_type is None):
            storage_type = HardDriveFactory.DEFAULT_STORAGE_TYPE

        if (hard_drive_driver is None):
            hard_drive_driver = HardDriveConfigBase.DEFAULT_DRIVER.name

        if (mcvirt_instance.initialiseNodes()):
            # Create disk images
            for hard_drive_size in hard_drives:
                HardDriveFactory.create(
                    vm_object=vm_object,
                    size=hard_drive_size,
                    storage_type=storage_type,
                    driver=hard_drive_driver)

            # If any have been specified, add a network configuration for each of the
            # network interfaces to the domain XML
            if (network_interfaces is not None):
                for network in network_interfaces:
                    network_object = Network(mcvirt_instance, network)
                    NetworkAdapter.create(vm_object, network_object)

        return vm_object

    def register(self, set_node=True):
        """Registers a VM with LibVirt"""
        from mcvirt.cluster.cluster import Cluster
        # Import domain XML template
        current_node = self.getNode()
        if (current_node is not None):
            raise VmAlreadyRegisteredException(
                'VM \'%s\' already registered on node: %s' %
                (self.name, current_node))

        if (Cluster.getHostname() not in self.getAvailableNodes()):
            raise UnsuitableNodeException(
                'VM \'%s\' cannot be registered on node: %s' %
                (self.name, Cluster.getHostname())
            )

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Activate hard disks
        for disk_object in self.getDiskObjects():
            disk_object.activateDisk()

        # Obtain domain XML
        domain_xml = ET.parse(MCVirt.TEMPLATE_DIR + '/domain.xml')

        # Add Name, RAM and CPU variables to XML
        domain_xml.find('./name').text = self.getName()
        domain_xml.find('./memory').text = self.getRAM()
        domain_xml.find('./vcpu').text = self.getCPU()

        device_xml = domain_xml.find('./devices')

        # Add hard drive configurations
        for hard_drive_object in self.getDiskObjects():
            drive_xml = hard_drive_object.getConfigObject()._generateLibvirtXml()
            device_xml.append(drive_xml)

        # Add network adapter configurations
        for network_adapter_object in self.getNetworkObjects():
            network_interface_xml = network_adapter_object._generateLibvirtXml()
            device_xml.append(network_interface_xml)

        domain_xml_string = ET.tostring(domain_xml.getroot(), encoding='utf8', method='xml')

        try:
            self.mcvirt_object.getLibvirtConnection().defineXML(domain_xml_string)
        except:
            raise MCVirtException('Error: An error occurred whilst registering VM')

        if (set_node):
            # Mark VM as being hosted on this machine
            self._setNode(Cluster.getHostname())

    def unregister(self):
        """Unregisters the VM from the local node"""
        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        self.ensureRegisteredLocally()

        # Remove VM from LibVirt
        try:
            self._getLibvirtDomainObject().undefine()
        except:
            raise MCVirtException('Failed to delete VM from libvirt')

        # De-activate the disk objects
        for disk_object in self.getDiskObjects():
            disk_object.deactivateDisk()

        # Remove node from VM configuration
        self._setNode(None)

    def _setNode(self, node):
        from mcvirt.cluster.cluster import Cluster
        if (self.mcvirt_object.initialiseNodes()):
            cluster_instance = Cluster(self.mcvirt_object)
            cluster_instance.runRemoteCommand('virtual_machine-setNode',
                                              {'vm_name': self.getName(),
                                               'node': node})

        # Update the node in the VM configuration
        def updateVmConfig(config):
            config['node'] = node
        self.getConfigObject().updateConfig(
            updateVmConfig, 'Changing node for VM \'%s\' to \'%s\'' %
            (self.getName(), node))

    def _getRemoteNodes(self):
        """Returns a list of remote available nodes"""
        from mcvirt.cluster.cluster import Cluster
        # Obtain list of available nodes
        nodes = self.getAvailableNodes()

        # Remove the local node from the list
        if (Cluster.getHostname() in nodes):
            nodes.remove(Cluster.getHostname())

        return nodes

    def isRegisteredLocally(self):
        """Returns true if the VM is registered on the local node"""
        from mcvirt.cluster.cluster import Cluster
        return (self.getNode() == Cluster.getHostname())

    def isRegisteredRemotely(self):
        """Returns true if the VM is registered on a remote node"""
        from mcvirt.cluster.cluster import Cluster
        return (not (self.getNode() == Cluster.getHostname() or self.getNode() is None))

    def isRegistered(self):
        """Returns true if the VM is registered on a node"""
        return (self.getNode() is not None)

    def ensureRegistered(self):
        """Ensures that the VM is registered"""
        if (not self.isRegistered()):
            raise VmNotRegistered('The VM %s is not registered on a node' % self.getName())

    def getNode(self):
        """Returns the node that the VM is registered on"""
        return self.getConfigObject().getConfig()['node']

    def getAvailableNodes(self):
        """Returns the nodes that the VM can be run on"""
        return self.getConfigObject().getConfig()['available_nodes']

    def ensureRegisteredLocally(self):
        """Ensures that the VM is registered locally, otherwise an exception is thrown"""
        if (not self.isRegisteredLocally()):
            raise VmRegisteredElsewhereException(
                'The VM \'%s\' is registered on the remote node: %s' %
                (self.getName(), self.getNode()))

    def getVncPort(self):
        """Returns the port used by the VNC display for the VM"""
        # Check the user has permission to view the VM console
        self.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.VIEW_VNC_CONSOLE,
            self)

        if (self.getPowerState() is not PowerStates.RUNNING):
            raise MCVirtException('The VM is not running')
        domain_xml = ET.fromstring(
            self._getLibvirtDomainObject().XMLDesc(
                libvirt.VIR_DOMAIN_XML_SECURE
            )
        )

        if (domain_xml.find('./devices/graphics[@type="vnc"]') is None):
            raise MCVirtException('VNC is not enabled on the VM')
        else:
            return domain_xml.find('./devices/graphics[@type="vnc"]').get('port')

    def ensureUnlocked(self):
        """Ensures that the VM is in an unlocked state"""
        if (self.getLockState() is LockStates.LOCKED):
            raise VirtualMachineLockException('VM \'%s\' is locked' % self.getName())

    def getLockState(self):
        """Returns the lock status of a VM"""
        return LockStates(self.getConfigObject().getConfig()['lock'])

    def setLockState(self, lock_status):
        """Sets the lock status of the VM"""
        # Ensure the user has permission to set VM locks
        self.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.SET_VM_LOCK, self)

        # Check if the lock is already set to this state
        if (self.getLockState() == lock_status):
            raise VirtualMachineLockException('Lock for \'%s\' is already set to \'%s\'' %
                                              (self.getName(), self.getLockState().name))

        def updateLock(config):
            config['lock'] = lock_status.value
        self.getConfigObject().updateConfig(updateLock, 'Setting lock state of \'%s\' to \'%s\'' %
                                                        (self.getName(), lock_status.name))

    def setBootOrder(self, boot_devices):
        """Sets the boot devices and the order in which devices are booted from"""

        def updateXML(domain_xml):
            old_boot_objects = domain_xml.findall('./os/boot')
            os_xml = domain_xml.find('./os')

            # Remove old boot XML configuration elements
            for old_boot_object in old_boot_objects:
                os_xml.remove(old_boot_object)

            # Add new boot XML configuration elements
            for new_boot_device in boot_devices:
                new_boot_xml_object = ET.Element('boot')
                new_boot_xml_object.set('dev', new_boot_device)

                # Append new XML configuration onto OS section of domain XML
                os_xml.append(new_boot_xml_object)

        self.editConfig(updateXML)

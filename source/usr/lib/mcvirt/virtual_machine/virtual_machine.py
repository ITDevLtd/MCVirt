"""Provides virtual machine class."""

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
import libvirt
import shutil
from texttable import Texttable
import time
import Pyro4

from mcvirt.constants import DirectoryLocation, PowerStates, LockStates
from mcvirt.exceptions import (MigrationFailureExcpetion, InsufficientPermissionsException,
                               VmAlreadyExistsException, LibvirtException,
                               VmAlreadyStoppedException, VmAlreadyStartedException,
                               VmAlreadyRegisteredException, VmRegisteredElsewhereException,
                               VmRunningException, VmStoppedException, UnsuitableNodeException,
                               VmNotRegistered, CannotStartClonedVmException,
                               CannotCloneDrbdBasedVmsException, CannotDeleteClonedVmException,
                               VirtualMachineLockException, InvalidArgumentException,
                               VirtualMachineDoesNotExistException, VmIsCloneException,
                               VncNotEnabledException, AttributeAlreadyChanged)
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.virtual_machine.disk_drive import DiskDrive
from mcvirt.virtual_machine.virtual_machine_config import VirtualMachineConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.lock import locking_method
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname
from mcvirt.argument_validator import ArgumentValidator


class VirtualMachine(PyroObject):
    """Provides operations to manage a LibVirt virtual machine."""

    OBJECT_TYPE = 'virtual machine'

    def __init__(self, virtual_machine_factory, name):
        """Set member variables and obtains LibVirt domain object."""
        self.name = name

        # Check that the domain exists
        if not virtual_machine_factory.check_exists(self.name):
            raise VirtualMachineDoesNotExistException(
                'Error: Virtual Machine does not exist: %s' % self.name
            )

    def get_remote_object(self):
        """Return a instance of the virtual machine object
        on the machine that the VM is registered
        """
        if self.isRegisteredLocally():
            return self
        elif self.isRegisteredRemotely():
            cluster = self._get_registered_object('cluster')
            remote_node = cluster.get_remote_node(self.getNode())
            remote_vm_factory = remote_node.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.getVirtualMachineByName(self.get_name())
            remote_node.annotate_object(remote_vm)
            return remote_vm
        else:
            raise VmNotRegistered('The VM is not registered on a node')

    def get_config_object(self):
        """Return the configuration object for the VM"""
        return VirtualMachineConfig(self)

    @Pyro4.expose()
    def get_name(self):
        """Return the name of the VM"""
        return self.name

    def _getLibvirtDomainObject(self):
        """Look up LibVirt domain object, based on VM name,
        and return object
        """
        # Get the domain object.
        return self._get_registered_object('libvirt_connector').get_connection().lookupByName(
            self.name
        )

    @Pyro4.expose()
    def get_libvirt_xml(self):
        """Obtain domain XML from libvirt"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SUPERUSER)
        return self._getLibvirtDomainObject().XMLDesc()

    @Pyro4.expose()
    @locking_method()
    def stop(self):
        """Stops the VM"""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        # Determine if VM is registered on the local machine
        if self.isRegisteredLocally():
            # Determine if VM is running
            if self._getPowerState() is PowerStates.RUNNING:
                try:
                    # Stop the VM
                    self._getLibvirtDomainObject().destroy()
                except Exception, e:
                    raise LibvirtException('Failed to stop VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('The VM is already shutdown')
        elif not self._cluster_disabled and self.isRegisteredRemotely():
            remote_vm = self.get_remote_object()
            remote_vm.stop()
        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    @locking_method()
    def start(self, iso_object=None):
        """Starts the VM"""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        if iso_object is not None:
            assert isinstance(self._convert_remote_object(iso_object),
                              self._get_registered_object('iso_factory').ISO_CLASS)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        if self.isRegisteredLocally():
            # Ensure VM hasn't been cloned
            if self.getCloneChildren():
                raise CannotStartClonedVmException('Cloned VMs cannot be started')

            # Determine if VM is stopped
            if self._getPowerState() is PowerStates.RUNNING:
                raise VmAlreadyStartedException('The VM is already running')

            for disk_object in self.getHardDriveObjects():
                disk_object.activateDisk()

            disk_drive_object = self.get_disk_drive()
            if iso_object:
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
                raise LibvirtException('Failed to start VM: %s' % e)

        elif not self._cluster_disabled and self.isRegisteredRemotely():
            cluster = self._get_registered_object('cluster')
            remote_node = cluster.get_remote_node(self.getNode())
            vm_factory = remote_node.get_connection('virtual_machine_factory')
            remote_vm = vm_factory.getVirtualMachineByName(self.get_name())
            remote_node.annotate_object(remote_vm)
            if iso_object:
                remote_iso_factory = remote_node.get_connection('iso_factory')
                remote_iso = remote_iso_factory.get_iso_by_name(iso_object.get_name())
                remote_node.annotate_object(remote_iso)
            else:
                remote_iso = None
            remote_vm.start(iso_object=remote_iso)

        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    @locking_method()
    def reset(self):
        """Resets the VM"""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        if self.isRegisteredLocally():
            # Determine if VM is running
            if self._getPowerState() is PowerStates.RUNNING:
                try:
                    # Reset the VM
                    self._getLibvirtDomainObject().reset()
                except Exception, e:
                    raise LibvirtException('Failed to reset VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('Cannot reset a stopped VM')
        elif self._is_cluster_master and self.isRegisteredRemotely():
            remote_vm = self.get_remote_object()
            remote_vm.reset()
        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Pyro4.expose()
    def getPowerState(self):
        return self._getPowerState().value

    def _getPowerState(self):
        """Returns the power state of the VM in the form of a PowerStates enum"""
        if self.isRegisteredLocally():
            if self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                return PowerStates.RUNNING
            else:
                return PowerStates.STOPPED

        elif self.isRegisteredRemotely() and not self._cluster_disabled:
            cluster = self._get_registered_object('cluster')
            remote_object = cluster.get_remote_node(self.getNode(), ignore_cluster_master=True)
            vm_factory = remote_object.get_connection('virtual_machine_factory')
            remote_vm = vm_factory.getVirtualMachineByName(self.get_name())
            remote_object.annotate_object(remote_vm)
            return PowerStates(remote_vm.getPowerState())
        else:
            return PowerStates.UNKNOWN

    @Pyro4.expose()
    def getInfo(self):
        """Gets information about the current VM"""
        warnings = ''

        if not self.isRegistered():
            warnings += 'Warning: Some details are not available' + \
                        " as the VM is not registered on a node\n"

        if self.isRegisteredRemotely():
            cluster = self._get_registered_object('cluster')
            remote_object = cluster.get_remote_node(self.getNode())
            remote_vm_factory = remote_object.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.getVirtualMachineByName(self.get_name())
            remote_object.annotate_object(remote_vm)
            return remote_vm.getInfo()

        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.add_row(('Name', self.get_name()))
        table.add_row(('CPU Cores', self.getCPU()))
        table.add_row(('Memory Allocation', str(int(self.getRAM()) / 1024) + 'MB'))
        table.add_row(('State', self._getPowerState().name))
        table.add_row(('Node', self.getNode()))
        table.add_row(('Available Nodes', ', '.join(self.getAvailableNodes())))

        # Display clone children, if they exist
        clone_children = self.getCloneChildren()
        if len(clone_children):
            table.add_row(('Clone Children', ','.join(clone_children)))

        # Display clone parent, if it exists
        clone_parent = self.getCloneParent()
        if clone_parent:
            table.add_row(('Clone Parent', clone_parent))

        # The ISO can only be displayed if the VM is on the local node
        if self.isRegisteredLocally():
            # Display the path of the attached ISO (if present)
            disk_object = self.get_disk_drive()
            iso_object = disk_object.getCurrentDisk()
            if iso_object:
                disk_name = iso_object.get_name()
            else:
                disk_name = None
        else:
            disk_name = 'Unavailable'

        if disk_name:
            table.add_row(('ISO location', disk_name))

        # Get info for each disk
        disk_objects = self.getHardDriveObjects()
        if len(disk_objects):
            table.add_row(('-- Disk ID --', '-- Disk Size --'))
            for disk_object in disk_objects:
                table.add_row(
                    (str(disk_object.disk_id),
                     str(int(disk_object.getSize()) / 1000) + 'GB')
                )
        else:
            warnings += "No hard disks present on machine\n"

        # Create info table for network adapters
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        if len(network_adapters) != 0:
            table.add_row(('-- MAC Address --', '-- Network --'))
            for network_adapter in network_adapters:
                table.add_row(
                    (network_adapter.getMacAddress(),
                     network_adapter.getConnectedNetwork()))
        else:
            warnings += "No network adapters present on machine\n"

        # Get information about the permissions for the VM
        table.add_row(('-- Group --', '-- Users --'))
        for permission_group in self._get_registered_object('auth').get_permission_groups():
            users = self._get_registered_object('auth').get_users_in_permission_group(
                permission_group,
                self
            )
            users_string = ','.join(users)
            table.add_row((permission_group, users_string))
        return table.draw() + "\n" + warnings

    @Pyro4.expose()
    @locking_method()
    def delete(self, remove_data=False, local_only=False):
        """Delete the VM - removing it from LibVirt and from the filesystem"""
        ArgumentValidator.validate_boolean(remove_data)
        ArgumentValidator.validate_boolean(local_only)

        # Check the user has permission to modify VMs or
        # that the user is the owner of the VM and the VM is a clone
        if not (self._get_registered_object('auth').check_permission(
                PERMISSIONS.MODIFY_VM, self) or
                (self.getCloneParent() and
                    self._get_registered_object('auth').check_permission(
                        PERMISSIONS.DELETE_CLONE, self))
                ):
            raise InsufficientPermissionsException(
                ('User does not have the required permission - '
                 'User must have MODIFY_VM permission or be the owner of the cloned VM')
            )

        # Determine if VM is running
        if self._is_cluster_master and self._getPowerState() == PowerStates.RUNNING:
            raise VmAlreadyStartedException('Error: Can\'t delete running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure that VM has not been cloned
        if self.getCloneChildren():
            raise CannotDeleteClonedVmException('Can\'t delete cloned VM')

        # If 'remove_data' has been passed as True, delete disks associated
        # with VM
        if remove_data and get_hostname() in self.getAvailableNodes():
            for disk_object in self.getHardDriveObjects():
                disk_object.delete()

        # 'Undefine' object from LibVirt
        if self.isRegisteredLocally():
            try:
                self._getLibvirtDomainObject().undefine()
            except:
                raise LibvirtException('Failed to delete VM from libvirt')

        # If VM is a clone of another VM, remove it from the configuration
        # of the parent
        if self.getCloneParent():
            def removeCloneChildConfig(vm_config):
                """Remove a given child VM from a parent VM configuration"""
                vm_config['clone_children'].remove(self.get_name())

            vm_factory = self._get_registered_object('virtual_machine_factory')
            parent_vm_object = vm_factory.getVirtualMachineByName(self.getCloneParent())
            parent_vm_object.get_config_object().update_config(
                removeCloneChildConfig, 'Removed clone child \'%s\' from \'%s\'' %
                (self.get_name(), self.getCloneParent()))

        # If 'remove_data' has been passed as True, delete directory
        # from VM storage
        if remove_data:
            # Remove VM configuration file
            self.get_config_object().gitRemove('VM \'%s\' has been removed' % self.name)
            shutil.rmtree(VirtualMachine._get_vm_dir(self.name))

        # Remove VM from MCVirt configuration
        def updateMCVirtConfig(config):
            config['virtual_machines'].remove(self.name)
        MCVirtConfig().update_config(
            updateMCVirtConfig,
            'Removed VM \'%s\' from global MCVirt config' %
            self.name)

        if self._is_cluster_master and not local_only:
            def remote_command(remote_object):
                vm_factory = remote_object.get_connection('virtual_machine_factory')
                remote_vm = vm_factory.getVirtualMachineByName(self.get_name())
                remote_object.annotate_object(remote_vm)
                remote_vm.delete(remove_data=remove_data)
            cluster = self._get_registered_object('cluster')
            remote_object = cluster.run_remote_command(remote_command)

    @Pyro4.expose()
    def getRAM(self):
        """Returns the amount of memory attached the VM"""
        return self.get_config_object().get_config()['memory_allocation']

    @Pyro4.expose()
    @locking_method()
    def updateRAM(self, memory_allocation, old_value):
        """Updates the amount of RAM allocated to a VM"""
        ArgumentValidator.validate_positive_integer(memory_allocation)
        ArgumentValidator.validate_positive_integer(old_value)

        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        if self.isRegisteredRemotely():
            vm_object = self.get_remote_object()
            return vm_object.updateRAM(memory_allocation, old_value)

        self.ensureRegisteredLocally()

        # Ensure memory_allocation is an interger, greater than 0
        try:
            int(memory_allocation)
            if int(memory_allocation) <= 0 or str(memory_allocation) != str(int(memory_allocation)):
                raise ValueError
        except ValueError:
            raise InvalidArgumentException('Memory allocation must be an integer greater than 0')

        current_value = self.getRAM()
        if old_value and current_value != old_value:
            raise AttributeAlreadyChanged(
                'Memory has already been changed to %s since command call' % current_value)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        def updateXML(domain_xml):
            # Update RAM allocation and unit measurement
            domain_xml.find('./memory').text = str(memory_allocation)
            domain_xml.find('./memory').set('unit', 'KiB')
            domain_xml.find('./currentMemory').text = str(memory_allocation)
            domain_xml.find('./currentMemory').set('unit', 'KiB')

        vm_object._editConfig(updateXML)

        # Update the MCVirt configuration
        vm_object.update_config(['memory_allocation'], str(memory_allocation),
                                'RAM allocation has been changed to %s' % memory_allocation)

    @Pyro4.expose()
    def getCPU(self):
        """Returns the number of CPU cores attached to the VM"""
        return self.get_config_object().get_config()['cpu_cores']

    @Pyro4.expose()
    @locking_method()
    def updateCPU(self, cpu_count, old_value):
        """Updates the number of CPU cores attached to a VM"""
        ArgumentValidator.validate_positive_integer(cpu_count)
        ArgumentValidator.validate_positive_integer(old_value)

        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        # Ensure cpu count is an interger, greater than 0
        try:
            int(cpu_count)
            if int(cpu_count) <= 0 or str(cpu_count) != str(int(cpu_count)):
                raise ValueError
        except ValueError:
            raise InvalidArgumentException('CPU count must be an integer greater than 0')

        current_value = self.getCPU()
        if old_value and current_value != old_value:
            raise AttributeAlreadyChanged(
                'CPU count has already been changed to %s since command call' % current_value)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Determine if VM is registered on the local machine
        self.ensureRegisteredLocally()

        def updateXML(domain_xml):
            # Update RAM allocation and unit measurement
            domain_xml.find('./vcpu').text = str(cpu_count)
        self._editConfig(updateXML)

        # Update the MCVirt configuration
        self.update_config(['cpu_cores'], str(cpu_count), 'CPU count has been changed to %s' %
                                                          cpu_count)

    @Pyro4.expose()
    def get_disk_drive(self):
        """Returns a disk drive object for the VM"""
        disk_drive_object = DiskDrive(self)
        self._register_object(disk_drive_object)
        return disk_drive_object

    @Pyro4.expose()
    def getHardDriveObjects(self):
        """Returns an array of disk objects for the disks attached to the VM"""
        disks = self.get_config_object().get_config()['hard_disks']
        hard_drive_factory = self._get_registered_object('hard_drive_factory')
        disk_objects = []
        for disk_id in disks:
            disk_objects.append(hard_drive_factory.getObject(self, disk_id))
        return disk_objects

    def update_config(self, attribute_path, value, reason):
        """Updates a VM configuration attribute and
           replicates change across all nodes"""
        # Update the local configuration
        def updateLocalConfig(config):
            config_level = config
            for attribute in attribute_path[:-1]:
                config_level = config_level[attribute]
            config_level[attribute_path[-1]] = value

        self.get_config_object().update_config(updateLocalConfig, reason)

        if self._is_cluster_master:
            def remote_command(remote_object):
                vm_factory = remote_object.get_connection('virtual_machine_factory')
                remote_vm = vm_factory.getVirtualMachineByName(self.get_name())
                remote_object.annotate_object(remote_vm)
                remote_vm.update_config(attribute_path=attribute_path, value=value,
                                        reason=reason)
            cluster = self._get_registered_object('cluster')
            remote_object = cluster.run_remote_command(remote_command)

    @staticmethod
    def _get_vm_dir(name):
        """Returns the storage directory for a given VM"""
        return DirectoryLocation.BASE_VM_STORAGE_DIR + '/' + name

    def getLibvirtConfig(self):
        """Returns an XML object of the libvirt configuration
        for the domain"""
        domain_flags = (libvirt.VIR_DOMAIN_XML_INACTIVE + libvirt.VIR_DOMAIN_XML_SECURE)
        domain_xml = ET.fromstring(self._getLibvirtDomainObject().XMLDesc(domain_flags))
        return domain_xml

    @Pyro4.expose()
    @locking_method()
    def editConfig(self, *args, **kwargs):
        """Provides permission checking around the editConfig method and
           exposes the method"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        return self._editConfig(*args, **kwargs)

    def _editConfig(self, callback_function):
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
            self._get_registered_object(
                'libvirt_connector').get_connection().defineXML(domain_xml_string)
        except:
            raise LibvirtException('Error: An error occurred whilst updating the VM')

    def getCloneParent(self):
        """Determines if a VM is a clone of another VM"""
        return self.get_config_object().get_config()['clone_parent']

    def getCloneChildren(self):
        """Returns the VMs that have been cloned from the VM"""
        return self.get_config_object().get_config()['clone_children']

    @Pyro4.expose()
    @locking_method()
    def offlineMigrate(self, destination_node_name, start_after_migration=False,
                       wait_for_vm_shutdown=False):
        """Performs an offline migration of a VM to another node in the cluster"""
        ArgumentValidator.validate_hostname(destination_node_name)
        ArgumentValidator.validate_boolean(start_after_migration)
        ArgumentValidator.validate_boolean(wait_for_vm_shutdown)

        if destination_node_name not in self.getAvailableNodes():
            raise UnsuitableNodeException('Node %s is not a valid node for this VM' %
                                          destination_node_name)

        # Ensure user has permission to migrate VM
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MIGRATE_VM, self)

        # Ensure the VM is locally registered
        self.ensureRegisteredLocally()

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is using a Drbd storage type
        self._preMigrationChecks(destination_node_name)

        # Check if VM is running
        while (self._getPowerState() is PowerStates.RUNNING):
            # Unless the user has specified to wait for the VM to shutdown, throw an exception
            # if the VM is running
            if not wait_for_vm_shutdown:
                raise VmRunningException(
                    'An offline migration can only be performed on a powered off VM. '
                    'Use --wait-for-shutdown to wait until the '
                    'VM is powered off before migrating.'
                )

            # Wait for 5 seconds before checking the VM state again
            time.sleep(5)

        # Unregister the VM on the local node
        self._unregister()

        # Register on remote node
        cluster = self._get_registered_object('cluster')
        remote = cluster.get_remote_node(destination_node_name)
        remote_vm_factory = remote.get_connection('virtual_machine_factory')
        remote_vm = remote_vm_factory.getVirtualMachineByName(self.get_name())
        remote.annotate_object(remote_vm)
        remote_vm.register()

        # Set the node of the VM
        self._setNode(destination_node_name)

        # If the user has specified to start the VM after migration, start it on
        # the remote node
        if start_after_migration:
            remote_vm.start()

    @Pyro4.expose()
    @locking_method()
    def onlineMigrate(self, destination_node_name):
        """Performs an online migration of a VM to another node in the cluster"""
        ArgumentValidator.validate_hostname(destination_node_name)

        # Ensure user has permission to migrate VM
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MIGRATE_VM, self)

        if destination_node_name not in self.getAvailableNodes():
            raise UnsuitableNodeException('Node %s is not a valid node for this VM' %
                                          destination_node_name)

        factory = self._get_registered_object('virtual_machine_factory')

        # Ensure VM is registered locally and unlocked
        self.ensureRegisteredLocally()
        self.ensureUnlocked()

        # Perform pre-migration checks
        self._preMigrationChecks(destination_node_name)

        # Perform online-migration-specific checks
        self._preOnlineMigrationChecks(destination_node_name)

        # Obtain cluster instance
        cluster = self._get_registered_object('cluster')

        # Obtain node object for destination node
        destination_node = cluster.get_remote_node(destination_node_name)

        # Begin pre-migration tasks
        try:
            # Obtain libvirt connection to destination node
            libvirt_connector = self._get_registered_object('libvirt_connector')
            destination_libvirt_connection = libvirt_connector.get_connection(
                destination_node_name
            )

            # Clear the VM node configuration
            self._setNode(None)

            # Perform pre-migration tasks on disk objects
            for disk_object in self.getHardDriveObjects():
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

            if not status:
                raise MigrationFailureExcpetion('Libvirt migration failed')

            # Perform post steps on hard disks and check disks
            for disk_object in self.getHardDriveObjects():
                disk_object.postOnlineMigration()
                disk_object._checkDrbdStatus()

            # Set the VM node to the destination node node
            self._setNode(destination_node_name)

        except Exception as e:
            # Determine which node the VM is present on
            vm_registration_found = False

            # Wait 10 seconds before performing the tear-down, as Drbd
            # will hold the block device open for a short period
            time.sleep(10)

            if self.get_name() in factory.getAllVmNames(node=get_hostname()):
                # VM is registered on the local node.
                vm_registration_found = True

                # Set Drbd on remote node to secondary
                for disk_object in self.getHardDriveObjects():
                    remote_disk = disk_object.get_remote_object(remote_node=destination_node)
                    remote_disk.drbdSetSecondary()

                # Re-register VM as being registered on the local node
                self._setNode(get_hostname())

            if self.get_name() in factory.getAllVmNames(node=destination_node_name):
                # Otherwise, if VM is registered on remote node, set the
                # local Drbd state to secondary
                vm_registration_found = True
                for disk_object in self.getHardDriveObjects():
                    time.sleep(10)
                    disk_object._drbdSetSecondary()

                # Register VM as being registered on the local node
                self._setNode(destination_node_name)

            # Reset disks
            for disk_object in self.getHardDriveObjects():
                # Reset dual-primary configuration
                disk_object._setTwoPrimariesConfig(allow=False)

                # Mark hard drives as being out-of-sync
                disk_object.setSyncState(False)
            raise

        # Perform post migration checks
        # Ensure VM is no longer registered with libvirt on the local node
        if self.get_name() in factory.getAllVmNames(node=get_hostname()):
            raise VmAlreadyRegisteredException(
                'The VM is unexpectedly registered with libvirt on the local node: %s' %
                self.get_name()
            )

        # Ensure VM is registered on the remote libvirt instance
        if self.get_name() not in factory.getAllVmNames(node=destination_node_name):
            raise VmNotRegistered(
                'The VM is unexpectedly not registered with libvirt on the destination node: %s' %
                destination_node_name
            )

        # Ensure VM is running on the remote node
        if self._getPowerState() is not PowerStates.RUNNING:
            raise VmStoppedException('VM is in unexpected %s power state after migration' %
                                     self._getPowerState())

    def _preMigrationChecks(self, destination_node_name):
        """Performs checks on the state of the VM to determine if is it suitable to
           be migrated"""
        # Ensure node is in the available nodes that the VM can be run on
        if destination_node_name not in self.getAvailableNodes():
            raise UnsuitableNodeException(
                'The remote node %s is not marked as being able to host the VM %s' %
                (destination_node_name, self.get_name()))

        # Obtain remote object for destination node
        cluster = self._get_registered_object('cluster')
        remote_node = cluster.get_remote_node(destination_node_name)
        remote_network_factory = remote_node.get_connection('network_factory')

        # Checks the Drbd state of the disks and ensure that they are
        # in a suitable state to be migrated
        for disk_object in self.getHardDriveObjects():
            disk_object.preMigrationChecks()

        # Check the remote node to ensure that the networks, that the VM is connected to,
        # exist on the remote node
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        for network_object in network_adapters:
            connected_network = network_object.getConnectedNetwork()
            if connected_network not in remote_network_factory.get_all_network_names():
                raise UnsuitableNodeException(
                    'The network %s does not exist on the remote node: %s' %
                    (connected_network, destination_node_name)
                )

    def _preOnlineMigrationChecks(self, destination_node_name):
        """Perform online-migration-specific pre-migration checks"""
        # Ensure any attached ISOs exist on the destination node
        disk_drive_object = self.get_disk_drive()
        disk_drive_object.preOnlineMigrationChecks(destination_node_name)

        # Ensure VM is powered on
        if self._getPowerState() is not PowerStates.RUNNING:
            raise VmStoppedException(
                'An online migration can only be performed on a running VM: %s' %
                self.get_name()
            )

    @Pyro4.expose()
    def getStorageType(self):
        """Returns the storage type of the VM"""
        return self.get_config_object().get_config()['storage_type']

    @Pyro4.expose()
    @locking_method()
    def clone(self, clone_vm_name):
        """Clones a VM, creating an identical machine, using
        LVM snapshotting to duplicate the Hard disk. Drbd is not
        currently supported
        """
        ArgumentValidator.validate_hostname(clone_vm_name)

        # Check the user has permission to create VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.CLONE_VM, self)

        # Ensure the storage type for the VM is not Drbd, as Drbd-based VMs cannot be cloned
        if self.getStorageType() == 'Drbd':
            raise CannotCloneDrbdBasedVmsException(
                'Cannot clone VM that uses Drbd-based storage: %s' %
                self.get_name()
            )

        # Determine if VM is running
        if self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            raise VmAlreadyStartedException('Can\'t clone running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure new VM name doesn't already exist
        if self._get_registered_object('virtual_machine_factory').check_exists(clone_vm_name):
            raise VirtualMachineDoesNotExistException('VM %s already exists' % clone_vm_name)

        # Ensure VM is not a clone, as cloning a cloned VM will cause issues
        if self.getCloneParent():
            raise VmIsCloneException('Cannot clone from a clone VM')

        # Create new VM for clone, without hard disks
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        networks = []
        for network_adapter in network_adapters:
            networks.append(network_adapter.getConnectedNetwork())
        vm_factory = self._get_registered_object('virtual_machine_factory')
        new_vm_object = vm_factory._create(clone_vm_name, self.getCPU(),
                                           self.getRAM(), [], networks,
                                           available_nodes=self.getAvailableNodes(),
                                           node=self.getNode())

        # Mark VM as being a clone and mark parent as being a clone
        def setCloneParent(vm_config):
            vm_config['clone_parent'] = self.get_name()

        new_vm_object.get_config_object().update_config(
            setCloneParent,
            'Set VM clone parent after initial clone')

        def setCloneChild(vm_config):
            vm_config['clone_children'].append(new_vm_object.get_name())

        self.get_config_object().update_config(
            setCloneChild,
            'Added new clone \'%s\' to VM configuration' %
            self.get_name())

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self._get_registered_object('auth').copy_permissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.getHardDriveObjects()
        for disk_object in disk_objects:
            disk_object.clone(new_vm_object)

        return new_vm_object

    @Pyro4.expose()
    @locking_method()
    def duplicate(self, duplicate_vm_name):
        """Duplicates a VM, creating an identical machine, making a
           copy of the storage"""
        ArgumentValidator.validate_hostname(duplicate_vm_name)

        # Check the user has permission to create VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.DUPLICATE_VM, self)

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Determine if VM is running
        if self._getLibvirtDomainObject().state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            raise VmAlreadyStartedException('Can\'t duplicate running VM')

        # Ensure new VM name doesn't already exist
        if self._get_registered_object('virtual_machine_factory').check_exists(duplicate_vm_name):
            raise VmAlreadyExistsException('VM already exists with name %s' % duplicate_vm_name)

        # Create new VM for clone, without hard disks
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        networks = []
        for network_adapter in network_adapters:
            networks.append(network_adapter.getConnectedNetwork())
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        new_vm_object = virtual_machine_factory._create(duplicate_vm_name, self.getCPU(),
                                                        self.getRAM(), [], networks,
                                                        available_nodes=self.getAvailableNodes(),
                                                        node=self.getNode())

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self._get_registered_object('auth').copy_permissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.getHardDriveObjects()
        for disk_object in disk_objects:
            disk_object.duplicate(new_vm_object)

        return new_vm_object

    @Pyro4.expose()
    @locking_method()
    def move(self, destination_node, source_node=None):
        """Move a VM from one node to another"""
        ArgumentValidator.validate_hostname(destination_node)
        if source_node is not None:
            ArgumentValidator.validate_hostname(source_node)

        # Ensure user has the ability to move VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MOVE_VM, self)

        cluster_instance = self._get_registered_object('cluster')

        # Ensure that the VM is registered on the local node
        self.ensureRegisteredLocally()

        # Set the source node as the local host, if the VM is VM
        # uses local-based storage
        if self.getStorageType() == 'Local':
            if source_node is None:
                source_node = get_hostname()

            # If migrating a local VM, since the only instance of the storage will be moved,
            # ensure that the VM is stopped
            if self._getPowerState() is not PowerStates.STOPPED:
                raise VmRunningException('VM must be stopped before performing a move')

        # Perform checks on source and remote nodes
        if destination_node == source_node:
            raise UnsuitableNodeException('Source node and destination node must' +
                                          ' be different nodes')
        if not cluster_instance.check_node_exists(source_node):
            raise UnsuitableNodeException('Source node does not exist: %s' % source_node)
        if not cluster_instance.check_node_exists(destination_node):
            raise UnsuitableNodeException('Destination node does not exist')
        if destination_node == get_hostname():
            raise UnsuitableNodeException('VM must be migrated to a remote node')
        if destination_node in self.getAvailableNodes():
            raise UnsuitableNodeException('Destination node is already' +
                                          ' an available node for the VM')
        if source_node not in self.getAvailableNodes():
            raise UnsuitableNodeException('Source node is not configured for the VM')

        # Ensure that, if the VM is Drbd-backed, that the local node is not the source
        if ((self.getStorageType() == 'Drbd' and
             source_node == get_hostname())):
            raise UnsuitableNodeException('Drbd-backed VMs must be moved on the node' +
                                          ' that will remain attached to the VM')

        # Remove the destination node from the list of available nodes for the VM and
        # add the remote node as an available node
        available_nodes = self.getAvailableNodes()
        available_nodes.remove(source_node)
        available_nodes.append(destination_node)
        self.update_config(['available_nodes'], available_nodes,
                           'Moved VM \'%s\' from node \'%s\' to node \'%s\'' %
                           (self.get_name(), source_node, destination_node))

        # Move each of the attached disks to the remote node
        for disk_object in self.getHardDriveObjects():
            disk_object.move(source_node=source_node, destination_node=destination_node)

        # If the VM is a Local VM, unregister it from the local node
        if self.getStorageType() == 'Local':
            self._unregister()

        # If the VM is a local VM, register it on the remote node
        if self.getStorageType() == 'Local':
            remote_node = cluster_instance.get_remote_node(destination_node)
            remote_vm_factory = remote_node.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.getVirtualMachineByName(self.get_name())
            remote_node.annotate_object(remote_vm)
            remote_vm.register()

    @Pyro4.expose()
    @locking_method()
    def register(self):
        """Public method for permforming VM register"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_VM_NODE, self
        )
        self._register()

    def _register(self, set_node=True):
        """Register a VM with LibVirt"""
        # Import domain XML template
        current_node = self.getNode()
        if current_node is not None:
            raise VmAlreadyRegisteredException(
                'VM \'%s\' already registered on node: %s' %
                (self.name, current_node))

        if get_hostname() not in self.getAvailableNodes():
            raise UnsuitableNodeException(
                'VM \'%s\' cannot be registered on node: %s' %
                (self.name, get_hostname())
            )

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Activate hard disks
        for disk_object in self.getHardDriveObjects():
            disk_object.activateDisk()

        # Obtain domain XML
        domain_xml = ET.parse(DirectoryLocation.TEMPLATE_DIR + '/domain.xml')

        # Add Name, RAM and CPU variables to XML
        domain_xml.find('./name').text = self.get_name()
        domain_xml.find('./memory').text = self.getRAM()
        domain_xml.find('./vcpu').text = self.getCPU()

        device_xml = domain_xml.find('./devices')

        # Add hard drive configurations
        for hard_drive_object in self.getHardDriveObjects():
            drive_xml = hard_drive_object._generateLibvirtXml()
            device_xml.append(drive_xml)

        # Add network adapter configurations
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        for network_adapter_object in network_adapters:
            network_interface_xml = network_adapter_object._generateLibvirtXml()
            device_xml.append(network_interface_xml)

        domain_xml_string = ET.tostring(domain_xml.getroot(), encoding='utf8', method='xml')

        try:
            self._get_registered_object(
                'libvirt_connector').get_connection().defineXML(domain_xml_string)
        except:
            raise LibvirtException('Error: An error occurred whilst registering VM')

        if set_node:
            # Mark VM as being hosted on this machine
            self._setNode(get_hostname())

    @Pyro4.expose()
    @locking_method()
    def unregister(self):
        """Public method for permforming VM unregister"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_VM_NODE, self
        )
        self._unregister()

    def _unregister(self):
        """Unregister the VM from the local node"""
        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        self.ensureRegisteredLocally()

        # Remove VM from LibVirt
        try:
            self._getLibvirtDomainObject().undefine()
        except:
            raise LibvirtException('Failed to delete VM from libvirt')

        # De-activate the disk objects
        for disk_object in self.getHardDriveObjects():
            disk_object.deactivateDisk()

        # Remove node from VM configuration
        self._setNode(None)

    def setNode(self, node):
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_VM_NODE, self
        )

    @Pyro4.expose()
    @locking_method()
    def setNodeRemote(self, node):
        """Set node from remote _setNode command"""
        if node is not None:
            ArgumentValidator.validate_hostname(node)
        # @TODO Merge with setNode and check either user type or permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        self._setNode(node)

    def _setNode(self, node):
        """Sets the node of the VM"""
        if self._is_cluster_master:
            # Update remote nodes
            def remote_command(remote_connection):
                vm_factory = remote_connection.get_connection('virtual_machine_factory')
                remote_vm = vm_factory.getVirtualMachineByName(self.get_name())
                remote_connection.annotate_object(remote_vm)
                remote_vm.setNodeRemote(node)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_command)

        # Update the node in the VM configuration
        def updateVmConfig(config):
            config['node'] = node
        self.get_config_object().update_config(
            updateVmConfig, 'Changing node for VM \'%s\' to \'%s\'' %
            (self.get_name(), node))

    def _get_remote_nodes(self):
        """Returns a list of remote available nodes"""
        # Obtain list of available nodes
        nodes = self.getAvailableNodes()

        # Remove the local node from the list
        if get_hostname() in nodes:
            nodes.remove(get_hostname())

        return nodes

    @Pyro4.expose()
    def isRegisteredLocally(self):
        """Returns true if the VM is registered on the local node"""
        return (self.getNode() == get_hostname())

    @Pyro4.expose()
    def isRegisteredRemotely(self):
        """Returns true if the VM is registered on a remote node"""
        return (not (self.getNode() == get_hostname() or self.getNode() is None))

    @Pyro4.expose()
    def isRegistered(self):
        """Returns true if the VM is registered on a node"""
        return (self.getNode() is not None)

    def ensureRegistered(self):
        """Ensures that the VM is registered"""
        if not self.isRegistered():
            raise VmNotRegistered('The VM %s is not registered on a node' % self.get_name())

    @Pyro4.expose()
    def getNode(self):
        """Returns the node that the VM is registered on"""
        return self.get_config_object().get_config()['node']

    def getAvailableNodes(self):
        """Returns the nodes that the VM can be run on"""
        return self.get_config_object().get_config()['available_nodes']

    def ensureRegisteredLocally(self):
        """Ensures that the VM is registered locally, otherwise an exception is thrown"""
        if not self.isRegisteredLocally():
            raise VmRegisteredElsewhereException(
                'The VM \'%s\' is registered on the remote node: %s' %
                (self.get_name(), self.getNode()))

    @Pyro4.expose()
    def getVncPort(self):
        """Returns the port used by the VNC display for the VM"""
        # Check the user has permission to view the VM console
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.VIEW_VNC_CONSOLE,
            self
        )

        if self._getPowerState() is not PowerStates.RUNNING:
            raise VmAlreadyStoppedException('The VM is not running')
        domain_xml = ET.fromstring(
            self._getLibvirtDomainObject().XMLDesc(
                libvirt.VIR_DOMAIN_XML_SECURE
            )
        )

        if domain_xml.find('./devices/graphics[@type="vnc"]') is None:
            raise VncNotEnabledException('VNC is not enabled on the VM')
        else:
            return domain_xml.find('./devices/graphics[@type="vnc"]').get('port')

    def ensureUnlocked(self):
        """Ensures that the VM is in an unlocked state"""
        if self._getLockState() is LockStates.LOCKED:
            raise VirtualMachineLockException('VM \'%s\' is locked' % self.get_name())

    @Pyro4.expose()
    def getLockState(self):
        return self._getLockState().value

    def _getLockState(self):
        """Returns the lock status of a VM"""
        return LockStates(self.get_config_object().get_config()['lock'])

    @Pyro4.expose()
    def setLockState(self, lock_status):
        ArgumentValidator.validate_integer(lock_status)
        return self._setLockState(LockStates(lock_status))

    def _setLockState(self, lock_status):
        """Sets the lock status of the VM"""
        # Ensure the user has permission to set VM locks
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SET_VM_LOCK, self)

        # Check if the lock is already set to this state
        if self._getLockState() == lock_status:
            raise VirtualMachineLockException('Lock for \'%s\' is already set to \'%s\'' %
                                              (self.get_name(), self._getLockState().name))

        def updateLock(config):
            config['lock'] = lock_status.value
        self.get_config_object().update_config(updateLock,
                                               'Setting lock state of \'%s\' to \'%s\'' %
                                               (self.get_name(), lock_status.name))

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

        self._editConfig(updateXML)

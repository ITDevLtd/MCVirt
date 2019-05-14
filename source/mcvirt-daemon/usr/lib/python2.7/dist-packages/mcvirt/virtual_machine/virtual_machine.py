"""Provides virtual machine class."""
# pylint: disable=
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
from time import sleep
from texttable import Texttable
from enum import Enum
import libvirt

from mcvirt.constants import DirectoryLocation, PowerStates, LockStates, AutoStartStates
from mcvirt.exceptions import (MigrationFailureExcpetion, InsufficientPermissionsException,
                               VmAlreadyExistsException, LibvirtException,
                               VmAlreadyStoppedException, VmAlreadyStartedException,
                               VmAlreadyRegisteredException, VmRegisteredElsewhereException,
                               VmRunningException, VmStoppedException, UnsuitableNodeException,
                               VmNotRegistered, CannotStartClonedVmException,
                               CannotCloneDrbdBasedVmsException, CannotDeleteClonedVmException,
                               VirtualMachineLockException, InvalidArgumentException,
                               VirtualMachineDoesNotExistException, VmIsCloneException,
                               VncNotEnabledException, AttributeAlreadyChanged,
                               InvalidModificationFlagException, MCVirtTypeError,
                               UsbDeviceAttachedToVirtualMachine, InvalidConfirmationCodeError,
                               DeleteProtectionAlreadyEnabledError, DeleteProtectionNotEnabledError,
                               DeleteProtectionEnabledError, ReachedMaximumStorageDevicesException,
                               VirtualMachineNotRegisteredWithLibvirt)
from mcvirt.syslogger import Syslogger
from mcvirt.virtual_machine.agent_connection import AgentConnection
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.virtual_machine.disk_drive import DiskDrive
from mcvirt.virtual_machine.usb_device import UsbDevice
from mcvirt.config.virtual_machine import VirtualMachine as VirtualMachineConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import get_hostname
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.utils import dict_merge
from mcvirt.size_converter import SizeConverter


class Modification(Enum):
    """An enum to represent the available modification flags."""

    WINDOWS = 'windows'


class VirtualMachine(PyroObject):
    """Provides operations to manage a LibVirt virtual machine."""

    OBJECT_TYPE = 'virtual machine'

    def __init__(self, _id):
        """Set member variables and obtains LibVirt domain object."""
        self._id = _id
        self.name = None
        self.disk_drive_object = None
        self.current_guest_memory_usage = None
        self.current_guest_cpu_usage = None

    @staticmethod
    def get_id_code():
        """Return default Id code for object."""
        return 'vm'

    def initialise(self):
        """Run after object is registered with pyro."""
        # Take the oportunity to update libvirt config
        self.check_libvirt_config_update()

    def __eq__(self, comp):
        """Allow for comparison of VM objects."""
        # Ensure class and name of object match
        if ('__class__' in dir(comp) and
                comp.__class__ == self.__class__ and
                'get_id' in dir(comp) and comp.get_id() == self.get_id()):
            return True

        # Otherwise return false
        return False

    def check_libvirt_config_update(self):
        """Determine if config updates need to be performed to libvirt."""
        config = self.get_config_object().get_config()
        # Determine if applied config is older than the config version and
        # VM is registered locally
        try:
            if (config['applied_version'] < config['version'] and
                    self.isRegisteredLocally() and
                    self.is_stopped):

                try:
                    # If so, unregister and re-register VM with libvirt
                    self._unregister()
                    self._register()

                    self.update_vm_config(
                        {'applied_version': config['version']},
                        'Update applied version',
                        nodes=self._get_registered_object('cluster').get_nodes(
                            include_local=True))
                except Exception:
                    # If the VM was unregistered from libvirt during the
                    # config migration, set it as unregistered
                    if self._get_libvirt_domain_object() is None:
                        self._setNode(None)

                    raise

        except Exception, exc:
            Syslogger.logger().warning('Error during VM config upgrade: %s: %s' % (
                self.get_name(), str(exc)))

    def get_remote_object(self, node=None, node_object=None, include_node=False,
                          set_cluster_master=False):
        """Return a instance of the virtual machine object
        on the machine that the VM is registered
        """
        # MUST check node parameter first first in both of these cases. As IF the
        # get_remote_object has been called when VM does not exist locally and a node
        # is specified, this will not check the local config file. Used whilst
        # deleting a VM
        if not node and self.isRegisteredLocally():
            return self
        elif node or self.isRegisteredRemotely():
            if not node_object:
                cluster = self._get_registered_object('cluster')
                node_object = cluster.get_remote_node(node or self.getNode(),
                                                      set_cluster_master=set_cluster_master)
            remote_vm_factory = node_object.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.get_virtual_machine_by_id(self.get_id())
            node_object.annotate_object(remote_vm)
            return remote_vm
        else:
            raise VmNotRegistered('The VM is not registered on a node')

    def get_config_object(self):
        """Return the configuration object for the VM."""
        return VirtualMachineConfig(self)

    @Expose(locking=True)
    def set_permission_config(self, config):
        """Set the permission config for the VM."""
        # Check permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        def update_vm_config(config):
            """Update the VM config."""
            config['permissions'] = config
        self.get_config_object().update_config(update_vm_config, 'Sync permissions')

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def update_vm_config(self, change_dict, reason, _f):
        """Update VM config using dict."""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def update_config(config):
            """Update the MCVirt config."""
            _f.add_undo_argument(original_config=dict(config))
            dict_merge(config, change_dict)

        self.get_config_object().update_config(update_config, reason)

    @Expose()
    def undo__update_vm_config(self, change_dict, reason, _f=None, original_config=None):
        """Undo config change."""
        self._get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def revert_config(config):
            """Revert config."""
            config = original_config

        if original_config is not None:
            self.get_config_object().update_config(
                revert_config,
                'Revert: %s' % reason)

    @Expose()
    def get_name(self):
        """Return the name of the VM."""
        if self.name is None:
            self.name = self.get_config_object().get_config()['name']
        return self.name

    @Expose()
    def get_id(self):
        """Return the ID of the VM."""
        return self.id_

    @property
    def id_(self):
        """Return ID."""
        return self._id

    def is_static(self):
        """Determine if node is statically defined to given nodes.
        This applies to nodes that use DRBD storage or those that use
        storage backends that is not shared
        """
        is_static = False
        for disk in self.get_hard_drive_objects():
            if disk.is_static():
                is_static = True

        # If nodes have been defined in the VM config, then the nodes
        # are static
        if self.get_config_object().get_config()['available_nodes'] is not None:
            is_static = True

        return is_static

    @Expose()
    def get_guest_cpu_usage(self):
        """Return value for cpu usage."""
        return self.current_guest_cpu_usage

    def get_guest_cpu_usage_text(self):
        """Obtain text for cpu usage."""
        if not self.isRegistered() or not self.is_running:
            return 'Not running'
        if self.current_guest_memory_usage is None:
            return 'Agent not running'
        vm = self.get_remote_object()
        return '%s%%' % vm.get_guest_cpu_usage()

    @Expose()
    def get_guest_memory_usage(self):
        """Return value for memory usage."""
        return self.current_guest_memory_usage

    def get_guest_memory_usage_text(self):
        """Obtain text for memory usage."""
        if not self.isRegistered() or not self.is_running:
            return 'Not running'
        if self.current_guest_memory_usage is None:
            return 'Agent not running'
        vm = self.get_remote_object()
        return '%s%%' % vm.get_guest_memory_usage()

    def _get_libvirt_domain_object(self, allow_remote=False, auto_register=True):
        """Look up LibVirt domain object, based on VM name,
        and return object
        """
        if self.isRegisteredRemotely():
            if allow_remote:
                libvirt_connection = self._get_registered_object(
                    'libvirt_connector').get_connection(server=self.getNode())
            else:
                raise VmRegisteredElsewhereException('Virtual machine is registered elsewhere')
        elif self.isRegisteredLocally():
            libvirt_connection = self._get_registered_object('libvirt_connector').get_connection()
        else:
            raise VmNotRegistered('VM is not registered')
        try:
            # Get the domain object.
            return libvirt_connection.lookupByName(
                self.get_name()
            )
        except libvirt.libvirtError, exc:
            # A libvirt error occured...
            # If the error is related to domain not existing...
            if 'Domain not found: no domain with matching name' in str(exc):
                # If the current session has a lock, then re-register with libvirt
                if self._has_lock and auto_register and self.isRegisteredLocally():
                    try:
                        self._register(set_node=False)
                        # Return with call from this method
                        return self._get_libvirt_domain_object(
                            allow_remote=allow_remote,
                            auto_register=False)
                    except Exception, exc2:
                        Syslogger.logger().error('Error whilst re-registering: %s' % str(exc2))
                else:
                    raise VirtualMachineNotRegisteredWithLibvirt(
                        'Virtual machine is not registered with libvirt')
            else:
                raise

    @Expose()
    def get_libvirt_xml(self):
        """Obtain domain XML from libvirt."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SUPERUSER)
        return self._get_libvirt_domain_object().XMLDesc()

    @property
    def is_running(self):
        """Return True if VM is running."""
        return self._get_power_state() is PowerStates.RUNNING

    @property
    def is_stopped(self):
        """Return true is VM is stopped."""
        return self._get_power_state() is PowerStates.STOPPED

    @Expose(locking=True)
    def stop(self):
        """Stops the VM."""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        # Determine if VM is registered on the local machine
        if self.isRegisteredLocally():
            # Determine if VM is running
            if self._get_power_state() is PowerStates.RUNNING:
                try:
                    # Stop the VM
                    self._get_libvirt_domain_object().destroy()
                except Exception, e:
                    raise LibvirtException('Failed to stop VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('The VM is already shutdown')
        elif not self._cluster_disabled and self.isRegisteredRemotely():
            remote_vm = self.get_remote_object()
            remote_vm.stop()

            # Take the oportunity to update libvirt config
            self.check_libvirt_config_update()
        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Expose(locking=True)
    def shutdown(self):
        """Shuts down the VM the VM."""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        # Determine if VM is registered on the local machine
        if self.isRegisteredLocally():
            # Determine if VM is running
            if self._get_power_state() is PowerStates.RUNNING:
                try:
                    # Shutdown the VM
                    self._get_libvirt_domain_object().shutdown()
                except Exception, e:
                    raise LibvirtException('Failed to stop VM: %s' % e)
            else:
                raise VmAlreadyStoppedException('The VM is already shutdown')
        elif not self._cluster_disabled and self.isRegisteredRemotely():
            remote_vm = self.get_remote_object()
            remote_vm.shutdown()
        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    def ensure_stopped(self):
        """Ensure VM is stopped."""
        if self._get_power_state() is not PowerStates.STOPPED:
            raise VmAlreadyStartedException('VM is not stopped')

    @Expose(locking=True)
    def start(self, iso_name=None):
        """Starts the VM."""
        # Check the user has permission to start/stop VMs
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.CHANGE_VM_POWER_STATE,
            self
        )

        # Is an iso is being attached, ensure the user has permissions to modify the VM
        if iso_name:
            self._get_registered_object('auth').assert_permission(
                PERMISSIONS.MODIFY_VM, self
            )

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered locally
        if self.isRegisteredLocally():
            # Ensure VM hasn't been cloned
            if self.getCloneChildren():
                raise CannotStartClonedVmException('Cloned VMs cannot be started')

            # Determine if VM is stopped
            if self._get_power_state() is PowerStates.RUNNING:
                raise VmAlreadyStartedException('The VM is already running')

            # Take the oportunity to update libvirt config
            self.check_libvirt_config_update()

            for disk_object in self.get_hard_drive_objects():
                disk_object.activateDisk()

            disk_drive_object = self.get_disk_drive()
            if iso_name:
                # If an ISO has been specified, attach it to the VM before booting
                # and adjust boot order to boot from ISO first
                iso_factory = self._get_registered_object('iso_factory')
                iso_object = iso_factory.get_iso_by_name(iso_name)
                disk_drive_object.attach_iso(iso_object)
                self.set_boot_order(['cdrom', 'hd'])
            else:
                # If not ISO was specified, remove any attached ISOs and change boot order
                # to boot from HDD
                disk_drive_object.remove_iso()
                self.set_boot_order(['hd'])

            # Start the VM
            try:
                self._get_libvirt_domain_object().create()
            except Exception, e:
                # Interogate exception to attempt to determine cause
                # of failure
                if 'Could not open ' in str(e) and ': Permission denied' in str(e):
                    # A disk could not be opened
                    # Iterate through hard drives and disk drive to determine
                    # which of these couldn't be opened
                    # @TODO complete
                    pass

                raise LibvirtException('Failed to start VM: %s' % e)

        elif not self._cluster_disabled and self.isRegisteredRemotely():
            cluster = self._get_registered_object('cluster')
            remote_node = cluster.get_remote_node(self.getNode())
            vm_factory = remote_node.get_connection('virtual_machine_factory')
            remote_vm = vm_factory.get_virtual_machine_by_name(self.get_name())
            remote_node.annotate_object(remote_vm)
            remote_vm.start(iso_name=iso_name)

        else:
            raise VmRegisteredElsewhereException(
                'VM registered elsewhere and cluster is not initialised'
            )

    @Expose(locking=True)
    def update_iso(self, iso_name=None):
        """Update the ISO attached to the VM."""
        # Ensure user has permissions to modify VM
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self
        )

        if self.isRegisteredRemotely():
            return self.get_remote_object().update_iso(iso_name)

        self.ensureRegisteredLocally()
        disk_drive = self.get_disk_drive()
        live = (self._get_power_state() is PowerStates.RUNNING)
        if iso_name:
            iso_factory = self._get_registered_object('iso_factory')
            iso_object = iso_factory.get_iso_by_name(iso_name)
            disk_drive.attach_iso(iso_object, live=live)

        else:
            disk_drive.remove_iso(live=live)

    @Expose(locking=True)
    def reset(self):
        """Reset the VM."""
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
            if self._get_power_state() is PowerStates.RUNNING:
                try:
                    # Reset the VM
                    self._get_libvirt_domain_object().reset()
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

    @Expose()
    def get_power_state(self):
        """Return the value of current power state."""
        return self._get_power_state().value

    def _get_power_state(self):
        """Return the power state of the VM in the form of a PowerStates enum."""
        if self.isRegistered():
            remote_libvirt = (self.isRegisteredRemotely() and not self._cluster_disabled)
            libvirt_object = self._get_libvirt_domain_object(allow_remote=remote_libvirt)
            if libvirt_object.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                return PowerStates.RUNNING
            else:
                return PowerStates.STOPPED
        else:
            return PowerStates.UNKNOWN

    @Expose()
    def get_agent_version_check_string(self):
        """Check agent version."""
        if not self.isRegistered():
            return 'VM is not registered'

        if self.isRegisteredRemotely():
            vm = self.get_remote_object()
            agent_version, host_version = vm.get_agent_version_check_string()
        else:
            try:
                agent_version, host_version = self.get_agent_connection().check_agent_version()
            except Exception, exc:
                return str(exc)

        if agent_version != host_version:
            return 'Agent Version: %s\nHost Version: %s' % (agent_version, host_version)
        else:
            return 'Up-to-date: %s' % agent_version

    @Expose(locking=True)
    def getInfo(self):
        """Get information about the current VM."""
        # Manually set permissions asserted, as this function can
        # run high privilege calls, but doesn't not require
        # permission checking
        self._get_registered_object('auth').set_permission_asserted()
        warnings = ''

        if not self.isRegistered():
            warnings += 'Warning: Some details are not available' + \
                        " as the VM is not registered on a node\n"

        if self.isRegisteredRemotely():
            cluster = self._get_registered_object('cluster')
            remote_object = cluster.get_remote_node(self.getNode())
            remote_vm_factory = remote_object.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.get_virtual_machine_by_name(self.get_name())
            remote_object.annotate_object(remote_vm)
            return remote_vm.getInfo()

        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.add_row(('Name', self.get_name()))
        table.add_row(('CPU Cores', self.getCPU()))
        table.add_row(('Guest CPU Usage', self.get_guest_cpu_usage_text()))
        table.add_row(('Memory Allocation', SizeConverter(self.getRAM()).to_string()))
        table.add_row(('Guest Memory Usage', self.get_guest_memory_usage_text()))
        table.add_row(('State', self._get_power_state().name))
        table.add_row(('Autostart', self._get_autostart_state().name))
        table.add_row(('Node', self.getNode()))
        table.add_row(('Available Nodes', ', '.join(self.getAvailableNodes())))
        table.add_row(('Lock State', self._getLockState().name))
        table.add_row(('Delete protection', ('Enabled'
                                             if self.get_delete_protection_state() else
                                             'Disabled')))
        table.add_row(('UUID', self.get_uuid()))
        table.add_row(('Graphics Driver', self.get_graphics_driver()))
        table.add_row(('Agent version', self.get_agent_version_check_string()))

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
        hdd_attachments = self.get_hard_drive_attachments()
        if len(hdd_attachments):
            table.add_row(('-- Disk ID --', '-- Disk Size --'))
            for attachment in sorted(hdd_attachments,
                                     key=lambda attachment: attachment.attachment_id):
                table.add_row((
                    str(attachment.attachment_id),
                    SizeConverter(
                        attachment.get_hard_drive_object().get_size()).to_string()))
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
        for group in self._get_registered_object('group_factory').get_all():
            users = group.get_users(virtual_machine=self)
            users_string = ','.join(sorted([user.get_username() for user in users]))
            table.add_row((group.name, users_string))
        return table.draw() + "\n" + warnings

    @Expose(locking=True)
    def delete(self, keep_disks=False, keep_config=False, local_only=False):
        """Delete the VM - removing it from LibVirt and from the filesystem."""
        ArgumentValidator.validate_boolean(keep_disks)
        ArgumentValidator.validate_boolean(keep_config)
        ArgumentValidator.validate_boolean(local_only)

        # Disable watchdog, if it exists
        self._get_registered_object('watchdog_factory').get_watchdog(self).cancel()

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

        # Manually set permission asserted, since we do a complex permission
        # check, which doesn't explicitly use assert_permission
        self._get_registered_object('auth').set_permission_asserted()

        # Delete if delete protection is enabled
        if self.get_delete_protection_state():
            raise DeleteProtectionEnabledError('VM is configured with delete protection')

        # Determine if VM is running
        if self._is_cluster_master and self._get_power_state() == PowerStates.RUNNING:
            raise VmAlreadyStartedException('Error: Can\'t delete running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure that VM has not been cloned
        if self.getCloneChildren():
            raise CannotDeleteClonedVmException('Can\'t delete cloned VM')

        # Unless 'keep_disks' has been passed as True, delete disks associated
        # with VM
        for hdd_attachment in self.get_hard_drive_attachments():
            hdd = hdd_attachment.get_hard_drive_object()

            # Remove hard drive attachment
            hdd_attachment.delete(local_only=local_only)

            if not keep_disks:
                hdd.delete(local_only=local_only)

        nodes = ([get_hostname()]
                 if local_only else
                 self._get_registered_object('cluster').get_nodes(include_local=True))

        self.delete_config(nodes=nodes, keep_config=keep_config)

    @Expose(locking=True, remote_nodes=True)
    def delete_config(self, keep_config):
        """Remove the VM config from the disk and MCVirt config."""
        # Unregister VM
        if self.isRegisteredLocally():
            self.unregister()

        # If VM is a clone of another VM, remove it from the configuration
        # of the parent
        if self.getCloneParent():
            def removeCloneChildConfig(vm_config):
                """Remove a given child VM from a parent VM configuration."""
                vm_config['clone_children'].remove(self.get_name())

            vm_factory = self._get_registered_object('virtual_machine_factory')
            parent_vm_object = vm_factory.get_virtual_machine_by_name(self.getCloneParent())
            parent_vm_object.get_config_object().update_config(
                removeCloneChildConfig, 'Removed clone child \'%s\' from \'%s\'' %
                (self.get_name(), self.getCloneParent()))

        # Remove VM from MCVirt configuration
        self.get_config_object().delete()

        vm_factory = self._get_registered_object('virtual_machine_factory')
        if self.id_ in vm_factory.CACHED_OBJECTS:
            del vm_factory.CACHED_OBJECTS[self.id_]
        self.unregister_object()

    @Expose()
    def getRAM(self):
        """Returns the amount of memory attached the VM."""
        return self.get_config_object().get_config()['memory_allocation']

    @Expose(locking=True)
    def update_ram(self, memory_allocation):
        """Updates the amount of RAM allocated to a VM."""
        # Convert memory and disk sizes to bytes
        memory_allocation = (memory_allocation
                             if memory_allocation is isinstance(memory_allocation, int) else
                             SizeConverter.from_string(memory_allocation).to_bytes())

        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        if self.isRegisteredRemotely():
            vm_object = self.get_remote_object(set_cluster_master=True)
            return vm_object.update_ram(memory_allocation)

        self.ensureRegisteredLocally()

        # Ensure VM is unlocked
        self.ensureUnlocked()

        def update_libvirt(domain_xml):
            """Update RAM allocation and unit measurement."""
            domain_xml.find('./memory').text = str(memory_allocation)
            domain_xml.find('./memory').set('unit', 'KiB')
            domain_xml.find('./currentMemory').text = str(memory_allocation)
            domain_xml.find('./currentMemory').set('unit', 'KiB')

        self.update_libvirt_config(update_libvirt)

        # Update the MCVirt configuration
        self.update_config(['memory_allocation'], str(memory_allocation),
                           'RAM allocation has been changed to %s' % memory_allocation)

    @Expose()
    def getCPU(self):
        """Returns the number of CPU cores attached to the VM."""
        return self.get_config_object().get_config()['cpu_cores']

    @Expose(locking=True)
    def update_cpu(self, cpu_count, old_value):
        """Updates the number of CPU cores attached to a VM."""
        ArgumentValidator.validate_positive_integer(cpu_count)
        ArgumentValidator.validate_positive_integer(old_value)

        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        if self.isRegisteredRemotely():
            vm_object = self.get_remote_object(set_cluster_master=True)
            return vm_object.update_cpu(cpu_count, old_value)

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

        if self.isRegistered():
            def update_libvirt(domain_xml):
                """Update RAM allocation and unit measurement."""
                domain_xml.find('./vcpu').text = str(cpu_count)
            self.update_libvirt_config(update_libvirt)

        # Update the MCVirt configuration
        self.update_config(['cpu_cores'], str(cpu_count), 'CPU count has been changed to %s' %
                                                          cpu_count)

    @Expose(locking=True, remote_nodes=True)
    def apply_cpu_flags(self):
        """Apply the XML changes for CPU flags."""
        self._get_registered_object('auth').assert_user_type(
            'ClusterUser',
            allow_indirect=True
        )

        flags = self.get_modification_flags()

        def update_libvirt(domain_xml):
            """Apply CPU flags to libvirt config."""
            cpu_section = domain_xml.find('./cpu')

            # Delete the CPU section if it already exists
            if cpu_section is not None:
                domain_xml.remove(cpu_section)

            if Modification.WINDOWS.value in flags:
                cpu_section = ET.Element('cpu', attrib={'mode': 'custom', 'match': 'exact'})
                domain_xml.append(cpu_section)

                model = ET.Element('model', attrib={'fallback': 'allow'})
                model.text = 'core2duo'
                feature = ET.Element('feature', attrib={'policy': 'require', 'name': 'nx'})

                cpu_section.append(model)
                cpu_section.append(feature)

        self.update_libvirt_config(update_libvirt)

    @Expose()
    def get_modification_flags(self):
        """Return a list of modification flags for this VM."""
        return self.get_config_object().get_config()['modifications']

    @staticmethod
    def check_modification_flag(flag):
        """Check that the provided flag name is valid."""
        if flag not in [i.value for i in Modification]:
            raise InvalidModificationFlagException('Invalid modification flag \'%s\'' % flag)

    @Expose(locking=True)
    def update_modification_flags(self, *args, **kwargs):
        """Update the modification flags for a VM."""

        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)
        return self._update_modification_flags(*args, **kwargs)

    def _update_modification_flags(self, add_flags=None, remove_flags=None):
        """Update the modification flags for a VM."""

        if add_flags is None:
            add_flags = []
        if remove_flags is None:
            remove_flags = []

        if self.isRegisteredRemotely():
            vm_object = self.get_remote_object(set_cluster_master=True)
            return vm_object.update_modification_flags(add_flags=add_flags,
                                                       remove_flags=remove_flags)

        self.ensureRegisteredLocally()

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Update the MCVirt configuration
        flags = self.get_modification_flags()

        # Add flags
        for flag in add_flags:
            VirtualMachine.check_modification_flag(flag)
            if flag not in flags:
                flags.append(flag)

        # Remove flags
        for flag in remove_flags:
            VirtualMachine.check_modification_flag(flag)
            if flag in flags:
                flags.remove(flag)

        flags_str = ', '.join(flags)
        self.update_config(['modifications'], flags,
                           'Modification flags has been set to: %s' % flags_str)

        # Apply CPU changes to libvirt configuration
        self.apply_cpu_flags()

    @Expose()
    def get_disk_drive(self):
        """Return a disk drive object for the VM."""
        if not self.disk_drive_object:
            self.disk_drive_object = DiskDrive(self)
            self._register_object(self.disk_drive_object)
        return self.disk_drive_object

    @Expose()
    def get_hard_drive_objects(self):
        """Return an array of disk objects for the disks attached to the VM."""
        return [attachment.get_hard_drive_object()
                for attachment in self.get_hard_drive_attachments()]

    @Expose()
    def get_hard_drive_attachments(self):
        """Return an array of hard drive attachments for the VM."""
        hard_drive_attachment_factory = self._get_registered_object(
            'hard_drive_attachment_factory')
        return hard_drive_attachment_factory.get_objects_by_virtual_machine(self)

    def get_attached_usb_devices(self):
        """Get USB devices attached to the VM."""
        libvirt_config = self.get_libvirt_config()
        device_list = []
        for device_config in libvirt_config.findall('./devices/hostdev[@type="usb"]'):
            device_address = device_config.find('./source/address')
            device_list.append(self._get_usb_device(device_address.get('bus'),
                                                    device_address.get('device')))
        return device_list

    @Expose(locking=True)
    def get_usb_device(self, bus, device):
        """Get USB object attached to the VM."""
        self.ensureRegisteredLocally()
        # Determine if device attached to another VM
        for vm_object in self._get_registered_object(
                'virtual_machine_factory').get_all_virtual_machines(node=self.getNode()):
            if (int(bus), int(device)) in [(dev.get_bus(), dev.get_device())
                                           for dev in vm_object.get_attached_usb_devices()]:
                if vm_object.get_name() != self.get_name():
                    raise UsbDeviceAttachedToVirtualMachine(
                        'USB device (%s, %s) is already attached to VM: %s' %
                        (bus, device, vm_object.get_name())
                    )
        return self._get_usb_device(bus, device)

    def _get_usb_device(self, bus, device):
        """Get Usb Device object."""
        # Create USB device object, register with daemon and return
        usb_device_object = UsbDevice(bus=bus, device=device, virtual_machine=self)
        self._register_object(usb_device_object)
        return usb_device_object

    @Expose()
    def remote_update_config(self, *args, **kwargs):
        """Provide an exposed method for update_config."""
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        return self.update_config(*args, **kwargs)

    def update_config(self, attribute_path, value, reason, local_only=False,
                      ignore_cluster_master=False):
        """Update a VM configuration attribute and
        replicates change across all nodes
        """
        # @TODO Merge with update_vm_config, moving the local_only
        # parameter to update_vm_config and rename update_vm_config
        # to update_config

        # Update the local configuration

        def update_local_config(config):
            """Update VM config."""
            config_level = config
            for attribute in attribute_path[:-1]:
                config_level = config_level[attribute]
            config_level[attribute_path[-1]] = value

        self.get_config_object().update_config(update_local_config, reason)

        if not local_only:
            def update_config_remote(remote_object):
                """Update remote VM config."""
                vm_factory = remote_object.get_connection('virtual_machine_factory')
                remote_vm = vm_factory.get_virtual_machine_by_name(self.get_name())
                remote_object.annotate_object(remote_vm)
                remote_vm.remote_update_config(attribute_path=attribute_path, value=value,
                                               reason=reason, local_only=True)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(
                update_config_remote,
                ignore_cluster_master=ignore_cluster_master)

    @staticmethod
    def get_vm_dir(name):
        """Return the storage directory for a given VM."""
        return DirectoryLocation.BASE_VM_STORAGE_DIR + '/' + name

    def get_libvirt_config(self):
        """Return an XML object of the libvirt configuration
        for the domain
        """
        domain_flags = (libvirt.VIR_DOMAIN_XML_INACTIVE + libvirt.VIR_DOMAIN_XML_SECURE)
        domain_xml = ET.fromstring(self._get_libvirt_domain_object().XMLDesc(domain_flags))
        return domain_xml

    @Expose(locking=True)
    def editConfig(self, *args, **kwargs):
        """Provides permission checking around the editConfig method and
        exposes the method
        """
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        return self.update_libvirt_config(*args, **kwargs)

    def update_libvirt_config(self, callback_function):
        """Provides an interface for updating the libvirt configuration, by obtaining
        the configuration, performing a callback function to perform changes on the
        configuration and pushing the configuration back into LibVirt
        """
        # Obtain VM XML
        domain_xml = self.get_libvirt_config()

        # Perform callback function to make changes to the XML
        callback_function(domain_xml)

        # Push XML changes back to LibVirt
        domain_xml_string = ET.tostring(domain_xml, encoding='utf8', method='xml')

        try:
            self._get_registered_object(
                'libvirt_connector').get_connection().defineXML(domain_xml_string)
        except Exception:
            raise LibvirtException('Error: An error occurred whilst updating the VM')

    def getCloneParent(self):
        """Determines if a VM is a clone of another VM."""
        return self.get_config_object().get_config()['clone_parent']

    def getCloneChildren(self):
        """Returns the VMs that have been cloned from the VM."""
        return self.get_config_object().get_config()['clone_children']

    @Expose(locking=True)
    def offlineMigrate(self, destination_node_name, start_after_migration=False,
                       wait_for_vm_shutdown=False):
        """Performs an offline migration of a VM to another node in the cluster."""
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
        while self._get_power_state() is PowerStates.RUNNING:
            # Unless the user has specified to wait for the VM to shutdown, throw an exception
            # if the VM is running
            if not wait_for_vm_shutdown:
                raise VmRunningException(
                    'An offline migration can only be performed on a powered off VM. '
                    'Use --wait-for-shutdown to wait until the '
                    'VM is powered off before migrating.'
                )

            # Wait for 5 seconds before checking the VM state again
            sleep(5)

        # Unregister the VM on the local node
        self._unregister()

        # Register on remote node
        cluster = self._get_registered_object('cluster')
        remote = cluster.get_remote_node(destination_node_name)
        remote_vm_factory = remote.get_connection('virtual_machine_factory')
        remote_vm = remote_vm_factory.get_virtual_machine_by_name(self.get_name())
        remote.annotate_object(remote_vm)
        self._register(node=destination_node_name)

        # If the user has specified to start the VM after migration, start it on
        # the remote node
        if start_after_migration:
            remote_vm.start()

    @Expose(locking=True)
    def onlineMigrate(self, destination_node_name):
        """Performs an online migration of a VM to another node in the cluster."""
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

            # Perform pre-migration tasks on disk objects
            for disk_object in self.get_hard_drive_objects():
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

            # Obtain libvirt domain object
            libvirt_domain_object = self._get_libvirt_domain_object()

            # Clear the VM node configuration
            self._setNode(None)

            # Perform migration
            status = libvirt_domain_object.migrate3(
                destination_libvirt_connection,
                params={},
                flags=migration_flags
            )

            if not status:
                raise MigrationFailureExcpetion('Libvirt migration failed')

            # Perform post steps on hard disks and check disks
            for disk_object in self.get_hard_drive_objects():
                disk_object.postOnlineMigration()
                disk_object._checkDrbdStatus()

            # Set the VM node to the destination node node
            self._setNode(destination_node_name)

        except Exception:
            # Wait 10 seconds before performing the tear-down, as Drbd
            # will hold the block device open for a short period
            sleep(10)

            if self.get_name() in factory.getAllVmNames(node=get_hostname()):
                # Set Drbd on remote node to secondary
                for disk_object in self.get_hard_drive_objects():
                    remote_disk = disk_object.get_remote_object(node_object=destination_node)
                    remote_disk.drbdSetSecondary()

                # Re-register VM as being registered on the local node
                self._setNode(get_hostname())

            if self.get_name() in factory.getAllVmNames(node=destination_node_name):
                # Otherwise, if VM is registered on remote node, set the
                # local Drbd state to secondary
                for disk_object in self.get_hard_drive_objects():
                    sleep(10)
                    disk_object._drbdSetSecondary()

                # Register VM as being registered on the local node
                self._setNode(destination_node_name)

            # Reset disks
            for disk_object in self.get_hard_drive_objects():
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
        if self._get_power_state() is not PowerStates.RUNNING:
            raise VmStoppedException('VM is in unexpected %s power state after migration' %
                                     self._get_power_state())

    def _preMigrationChecks(self, destination_node_name):
        """Performs checks on the state of the VM to determine if is it suitable to
           be migrated."""
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
        for disk_object in self.get_hard_drive_objects():
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
        """Perform online-migration-specific pre-migration checks."""
        # Ensure any attached ISOs exist on the destination node
        disk_drive_object = self.get_disk_drive()
        disk_drive_object.preOnlineMigrationChecks(destination_node_name)

        # Ensure VM is powered on
        if self._get_power_state() is not PowerStates.RUNNING:
            raise VmStoppedException(
                'An online migration can only be performed on a running VM: %s' %
                self.get_name()
            )

    @Expose()
    def getStorageType(self):
        """Returns the storage type of the VM."""
        for hdd in self.get_hard_drive_objects():
            return hdd.get_type()

        return None

    @Expose(locking=True)
    def clone(self, clone_vm_name, retain_mac=False):
        """Clones a VM, creating an identical machine, using
        LVM snapshotting to duplicate the Hard disk. Drbd is not
        currently supported
        """
        ArgumentValidator.validate_hostname(clone_vm_name)

        # Check the user has permission to create VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.CLONE_VM, self)

        # Ensure VM is registered locally
        self.ensureRegisteredLocally()

        # Ensure the storage type for the VM is not Drbd, as Drbd-based VMs cannot be cloned
        if self.getStorageType() == 'Drbd':
            raise CannotCloneDrbdBasedVmsException(
                'Cannot clone VM that uses Drbd-based storage: %s' %
                self.get_name()
            )

        # Determine if VM is running
        if self._get_libvirt_domain_object().state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            raise VmAlreadyStartedException('Can\'t clone running VM')

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure new VM name doesn't already exist
        if self._get_registered_object(
                'virtual_machine_factory').check_exists_by_name(clone_vm_name):
            raise VirtualMachineDoesNotExistException('VM %s already exists' % clone_vm_name)

        # Ensure VM is not a clone, as cloning a cloned VM will cause issues
        if self.getCloneParent():
            raise VmIsCloneException('Cannot clone from a clone VM')

        # Create new VM for clone, without hard disks
        vm_factory = self._get_registered_object('virtual_machine_factory')
        new_vm_object = vm_factory._create(clone_vm_name,
                                           self.getCPU(),
                                           self.getRAM(),
                                           available_nodes=self.getAvailableNodes(),
                                           node=self.getNode(),
                                           is_static=self.is_static())

        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        for network_adapter in network_adapters:
            network_adapter_factory.create(new_vm_object, network_adapter.get_network_object(),
                                           network_adapter.getMacAddress() if retain_mac else None)

        # Mark VM as being a clone and mark parent as being a clone
        def set_clone_parent(vm_config):
            """Update clone parent config."""
            vm_config['clone_parent'] = self.get_name()

        new_vm_object.get_config_object().update_config(
            set_clone_parent,
            'Set VM clone parent after initial clone')

        def set_clone_child(vm_config):
            """Set clone children config in new VM."""
            vm_config['clone_children'].append(new_vm_object.get_name())

        self.get_config_object().update_config(
            set_clone_child,
            'Added new clone \'%s\' to VM configuration' %
            self.get_name())

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self._get_registered_object('auth').copy_permissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.get_hard_drive_objects()
        for disk_object in disk_objects:
            disk_object.clone(new_vm_object)

        return new_vm_object

    @Expose(locking=True)
    def duplicate(self, duplicate_vm_name, storage_backend=None, retain_mac=False):
        """Duplicates a VM, creating an identical machine, making a
           copy of the storage."""
        ArgumentValidator.validate_hostname(duplicate_vm_name)

        # Check the user has permission to create VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.DUPLICATE_VM, self)

        # Ensure VM is registered locally
        self.ensureRegisteredLocally()

        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Determine if VM is running
        if self._get_libvirt_domain_object().state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            raise VmAlreadyStartedException('Can\'t duplicate running VM')

        # Ensure new VM name doesn't already exist
        if self._get_registered_object(
                'virtual_machine_factory').check_exists_by_name(duplicate_vm_name):
            raise VmAlreadyExistsException('VM already exists with name %s' % duplicate_vm_name)

        # Create new VM for clone, without hard disks
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')

        new_vm_object = virtual_machine_factory._create(duplicate_vm_name, self.getCPU(),
                                                        self.getRAM(), [], [],
                                                        available_nodes=self.getAvailableNodes(),
                                                        node=self.getNode(),
                                                        storage_backend=storage_backend)

        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        for network_adapter in network_adapters:
            network_adapter_factory.create(new_vm_object, network_adapter.get_network_object(),
                                           network_adapter.getMacAddress() if retain_mac else None)

        # Set current user as an owner of the new VM, so that they have permission
        # to perform functions on the VM
        self._get_registered_object('auth').copy_permissions(self, new_vm_object)

        # Clone the hard drives of the VM
        disk_objects = self.get_hard_drive_objects()
        for disk_object in disk_objects:
            disk_object.duplicate(new_vm_object, storage_backend=storage_backend)

        return new_vm_object

    @Expose(locking=True)
    def move(self, destination_node, source_node=None):
        """Move a VM from one node to another."""
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
            if self._get_power_state() is not PowerStates.STOPPED:
                raise VmRunningException('VM must be stopped before performing a move')

        # Perform checks on source and remote nodes
        if destination_node == source_node:
            raise UnsuitableNodeException('Source node and destination node must' +
                                          ' be different nodes')
        if not cluster_instance.check_node_exists(source_node, include_local=True):
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
        if (self.getStorageType() == 'Drbd' and
                source_node == get_hostname()):
            raise UnsuitableNodeException('Drbd-backed VMs must be moved on the node' +
                                          ' that will remain attached to the VM')
        elif self.getStorageType() == 'Local':
            raise UnsuitableNodeException('Local-based storage VMs cannot be moved')

        # Ensure that the destination node will support the volume
        storage_backend = None
        total_hdd_size = 0
        for disk_object in self.get_hard_drive_objects():
            storage_backend = disk_object.storage_backend
            total_hdd_size += disk_object.get_size()
        # Force check for 'Local' storage, as we're only specifying one node,
        # as otherwise the check will ensure that there is the additional space
        # on the remaining node.
        self._get_registered_object('hard_drive_factory').ensure_hdd_valid(
            size=total_hdd_size, storage_type='Local',
            nodes=[destination_node], storage_backend=storage_backend,
            nodes_predefined=True)

        # Remove the destination node from the list of available nodes for the VM and
        # add the remote node as an available node
        available_nodes = self.getAvailableNodes()
        available_nodes.remove(source_node)
        available_nodes.append(destination_node)
        self.update_config(['available_nodes'], available_nodes,
                           'Moved VM \'%s\' from node \'%s\' to node \'%s\'' %
                           (self.get_name(), source_node, destination_node))

        # Move each of the attached disks to the remote node
        for disk_object in self.get_hard_drive_objects():
            disk_object.move(source_node=source_node, destination_node=destination_node)

        # If the VM is a Local VM, unregister it from the local node
        if self.getStorageType() == 'Local':
            self._unregister()

        # If the VM is a local VM, register it on the remote node
        if self.getStorageType() == 'Local':
            remote_node = cluster_instance.get_remote_node(destination_node)
            remote_vm_factory = remote_node.get_connection('virtual_machine_factory')
            remote_vm = remote_vm_factory.get_virtual_machine_by_name(self.get_name())
            remote_node.annotate_object(remote_vm)
            remote_vm.register()

    def get_uuid(self):
        """Returns the Libvirt UUID for the VM."""
        # If the UUID is stored in the MCVirt configuration, return it
        config_uuid = self.get_config_object().get_config()['uuid']
        if config_uuid:
            return config_uuid

        # Determine if VM is registered, and obtain libvirt uuid
        if self.isRegistered():
            domain_xml = ET.fromstring(
                self._get_libvirt_domain_object().XMLDesc(
                    libvirt.VIR_DOMAIN_XML_SECURE
                )
            )
            uuid = domain_xml.find('./uuid').text

            # Store UUID in MCVirt VM config
            self.update_config(
                ['uuid'], uuid,
                'Set UUID for VM from Libvirt',
                ignore_cluster_master=True
            )

            return uuid

        return None

    @Expose(locking=True)
    def register(self, node=None):
        """Public method for permforming VM register."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_VM_NODE, self
        )
        self._register(node=node)

    @Expose(locking=True, expose=False, undo_method='_unregister')
    def _register(self, set_node=True, node=None):
        """Register a VM with LibVirt."""
        # Import domain XML template
        current_node = self.getNode()
        node = get_hostname() if node is None else node

        # Ensure that the current node is not set OR
        # it is currently registered on the local node
        if (current_node is not None and
                current_node != node):
            raise VmAlreadyRegisteredException(
                'VM \'%s\' already registered on node: %s' %
                (self.get_name(), current_node))

        if get_hostname() not in self.getAvailableNodes():
            raise UnsuitableNodeException(
                'VM \'%s\' cannot be registered on node: %s' %
                (self.get_name(), node)
            )

        # Ensure VM is unlocked
        self.ensureUnlocked()

        self.register_on_node(nodes=[node])

        if set_node:
            # Mark VM as being hosted on this machine
            self._setNode(node)

        self.apply_cpu_flags(nodes=[node])

    @Expose(locking=True, remote_nodes=True)
    def register_on_node(self):
        """Perform actual registration on node."""
        self._get_registered_object('auth').assert_user_type(
            'ClusterUser',
            allow_indirect=True
        )

        # Activate hard disks
        for disk_object in self.get_hard_drive_objects():
            # Activate on local node
            disk_object.activateDisk()

        # Obtain domain XML
        domain_xml = ET.parse(DirectoryLocation.TEMPLATE_DIR + '/domain.xml')

        uuid = self.get_uuid()
        if uuid:
            uuid_xml = ET.Element('uuid')
            uuid_xml.text = uuid
            domain_xml.getroot().append(uuid_xml)

        # Add Name, RAM, CPU and graphics driver variables to XML
        domain_xml.find('./name').text = self.get_name()
        domain_xml.find('./memory').text = '%s' % str(self.getRAM())
        domain_xml.find('./memory').set('unit', 'b')
        domain_xml.find('./vcpu').text = str(self.getCPU())
        domain_xml.find('./devices/video/model').set('type', self.get_graphics_driver())

        device_xml = domain_xml.find('./devices')

        # Add hard drive configurations
        hard_drive_attachment_factory = self._get_registered_object(
            'hard_drive_attachment_factory')
        for hard_drive_object in hard_drive_attachment_factory.get_objects_by_virtual_machine(
                self):
            drive_xml = hard_drive_object.generate_libvirt_xml()
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
        except Exception, e:
            try:
                Syslogger.logger().error('Libvirt error whilst registering %s:\n%s' %
                                         (self.get_name(), str(e)))
            except Exception:
                pass
            raise LibvirtException('Error: An error occurred whilst registering VM')

        # If UUID was initially not found, re-obtain it, to store
        # the UUID generated by Libvirt
        self.get_uuid()

    @Expose(locking=True, undo_method='_register')
    def unregister(self):
        """Public method for permforming VM unregister."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_VM_NODE, self
        )
        self._unregister()

    @Expose(expose=False)
    def _unregister(self, *args, **kwrags):
        """Unregister the VM from the local node."""
        # Ensure VM is unlocked
        self.ensureUnlocked()

        # Ensure VM is registered
        self.ensureRegistered()

        self.unregister_on_node(nodes=[self.getNode()])

        # Remove node from VM configuration
        self._setNode(None)

    @Expose(locking=True, remote_nodes=True)
    def unregister_on_node(self):
        """Perform actual unregistration."""
        # Remove VM from LibVirt
        try:
            self._get_libvirt_domain_object(auto_register=False).undefine()
        except VirtualMachineNotRegisteredWithLibvirt:
            Syslogger.logger().warn(
                'VM not registered with libvirt whilst attempting to unregister: %s' %
                self.get_name())
        except Exception, exc:
            Syslogger.logger().error('Libvirt error: %s' % str(exc))
            raise LibvirtException('Failed to delete VM from libvirt')

        # De-activate the disk objects
        for disk_object in self.get_hard_drive_objects():
            disk_object.deactivateDisk()

    @Expose(locking=True)
    def setNodeRemote(self, node):
        """Set node from remote _setNode command."""
        if node is not None:
            ArgumentValidator.validate_hostname(node)
        # @TODO Merge with setNode and check either user type or permissions
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        self._setNode(node)

    def _setNode(self, node):
        """Sets the node of the VM."""
        self.update_vm_config(
            {'node': node},
            'Update node for %s to %s' % (self.get_name(), node),
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    def _get_remote_nodes(self):
        """Returns a list of remote available nodes."""
        # @TODO rename ot get_remote_nodes
        # Obtain list of available nodes
        nodes = self.getAvailableNodes()

        # Remove the local node from the list
        if get_hostname() in nodes:
            nodes.remove(get_hostname())

        return nodes

    @Expose()
    def isRegisteredLocally(self):
        """Returns true if the VM is registered on the local node."""
        return self.getNode() == get_hostname()

    @Expose()
    def isRegisteredRemotely(self):
        """Returns true if the VM is registered on a remote node."""
        return not (self.getNode() == get_hostname() or self.getNode() is None)

    @Expose()
    def isRegistered(self):
        """Returns true if the VM is registered on a node."""
        return self.getNode() is not None

    def ensureRegistered(self):
        """Ensures that the VM is registered."""
        if not self.isRegistered():
            raise VmNotRegistered('The VM %s is not registered on a node' % self.get_name())

    @Expose()
    def getNode(self):
        """Returns the node that the VM is registered on."""
        return self.get_config_object().get_config()['node']

    def getStorageNodes(self):
        """Defines the nodes that the storage is available to for the VM.
        Unlike getAvailableNodes, this does not change based on whether VM
        requirements exist on the node (e.g. avialable networks)
        """
        # TODO use this method during creation of storage
        return self.getAvailableNodes()

    def getAvailableNodes(self):
        """Returns the nodes that the VM can be run on."""
        # If the VM is static, return the nodes from the config file
        if self.is_static():
            return self.get_config_object().get_config()['available_nodes']

        # Otherwise, calculate which nodes the VM can be run on...
        cluster = self._get_registered_object('cluster')

        # Obtain list of required network and storage backends
        storage_backends = [hdd.storage_backend for hdd in self.get_hard_drive_objects()]
        network_adapter_factory = self._get_registered_object('network_adapter_factory')
        network_adapters = network_adapter_factory.getNetworkAdaptersByVirtualMachine(self)
        networks = [network_adapter.get_network_object() for network_adapter in network_adapters]

        # Obtain list of available nodes from cluster
        return cluster.get_compatible_nodes(storage_backends=storage_backends, networks=networks)

    def ensureRegisteredLocally(self):
        """Ensures that the VM is registered locally, otherwise an exception is thrown."""
        if not self.isRegisteredLocally():
            node = self.getNode()
            if node:
                raise VmRegisteredElsewhereException(
                    'The VM \'%s\' is registered on the remote node: %s' %
                    (self.get_name(), self.getNode()))
            else:
                raise VmRegisteredElsewhereException(
                    'VM \'%s\' is not registered on a node' % self.get_name()
                )

    @Expose()
    def getVncPort(self):
        """Returns the port used by the VNC display for the VM."""
        # Check the user has permission to view the VM console
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.VIEW_VNC_CONSOLE,
            self
        )

        if self._get_power_state() is not PowerStates.RUNNING:
            raise VmAlreadyStoppedException('The VM is not running')
        domain_xml = ET.fromstring(
            self._get_libvirt_domain_object().XMLDesc(
                libvirt.VIR_DOMAIN_XML_SECURE
            )
        )

        if domain_xml.find('./devices/graphics[@type="vnc"]') is None:
            raise VncNotEnabledException('VNC is not enabled on the VM')
        else:
            return domain_xml.find('./devices/graphics[@type="vnc"]').get('port')

    def get_agent_connection(self):
        """Obtain an agent connection object."""
        return AgentConnection(self)

    def get_host_agent_path(self):
        """Obtain the path of the serial interface for the VM on the host."""
        if self._get_power_state() is not PowerStates.RUNNING:
            raise VmAlreadyStoppedException('The VM is not running')
        domain_xml = ET.fromstring(
            self._get_libvirt_domain_object().XMLDesc(
                libvirt.VIR_DOMAIN_XML_SECURE
            )
        )
        if domain_xml.find(
                './devices/serial[@type="pty"]/target[@port="0"]/../source') is None:
            raise VncNotEnabledException('Serial port cannot be found for VM')
        else:
            return domain_xml.find(
                './devices/serial[@type="pty"]/target[@port="0"]/../source').get('path')

    def get_agent_timeout(self):
        """Obtain agent timeout from config."""
        timeout = self.get_config_object().get_config()['agent']['connection_timeout']
        if timeout is None:
            timeout = MCVirtConfig().get_config()['agent']['connection_timeout']

        return timeout

    def is_watchdog_enabled(self):
        """Obtain watchdog interval from config."""
        return self.get_config_object().get_config()['watchdog']['enabled']

    @Expose(locking=True)
    def set_watchdog_status(self, status):
        """Update the status of the watchdog."""
        # Validate status boolean
        ArgumentValidator.validate_boolean(status)

        # Check permissions
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self)

        self.update_vm_config(
            change_dict={'watchdog': {'enabled': status}},
            reason='Update watchdog status',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def set_watchdog_interval(self, interval):
        """Set VM watchdog interval."""
        # Validate interval
        if interval is not None:
            ArgumentValidator.validate_positive_integer(interval)

        # Check permissions
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self)

        self.update_vm_config(
            change_dict={'watchdog': {'interval': interval}},
            reason='Update watchdog interval',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def set_watchdog_reset_fail_count(self, count):
        """Update reset fail count for watchdog."""
        if count is not None:
            ArgumentValidator.validate_positive_integer(count)

        # Check permissions
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self)

        self.update_vm_config(
            change_dict={'watchdog': {'reset_fail_count': count}},
            reason='Update watchdog reset fail count',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def set_watchdog_boot_wait(self, wait):
        """Update boot wait for watchdog."""
        if wait is not None:
            ArgumentValidator.validate_positive_integer(wait)

        # Check permissions
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self)

        self.update_vm_config(
            change_dict={'watchdog': {'boot_wait': wait}},
            reason='Update watchdog boot wait',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    def get_watchdog_interval(self):
        """Obtain watchdog interval from config."""
        interval = self.get_config_object().get_config()['watchdog']['interval']
        if interval is None:
            interval = MCVirtConfig().get_config()['watchdog']['interval']

        return interval

    def get_watchdog_boot_wait(self):
        """Obtain watchdog interval from config."""
        boot_wait = self.get_config_object().get_config()['watchdog']['boot_wait']
        if boot_wait is None:
            boot_wait = MCVirtConfig().get_config()['watchdog']['boot_wait']

        return boot_wait

    def get_watchdog_reset_fail_count(self):
        """Obtain watchdog interval from config."""
        reset_fail_count = self.get_config_object().get_config()['watchdog'][
            'reset_fail_count']
        if reset_fail_count is None:
            reset_fail_count = MCVirtConfig().get_config()['watchdog']['reset_fail_count']

        return reset_fail_count

    def ensureUnlocked(self):
        """Ensures that the VM is in an unlocked state."""
        if self._getLockState() is LockStates.LOCKED:
            raise VirtualMachineLockException('VM \'%s\' is locked' % self.get_name())

    @Expose(locking=True)
    def set_autostart_state(self, state):
        """Set the autostart state of the VM."""
        # Ensure the state is valid
        try:
            autostart = AutoStartStates[state]
        except TypeError:
            raise MCVirtTypeError('Invalid autostart state')
        self.update_config(['autostart'], autostart.value, 'Update autostart')

    @Expose()
    def get_autostart_state(self):
        """Return the enum value for autostart."""
        return self._get_autostart_state().value

    def _get_autostart_state(self):
        """Return the autostart enum."""
        return AutoStartStates(self.get_config_object().get_config()['autostart'])

    @Expose()
    def getLockState(self):
        """Return the lock state for the VM."""
        return self._getLockState().value

    def _getLockState(self):
        """Returns the lock status of a VM."""
        return LockStates(self.get_config_object().get_config()['lock'])

    @Expose(locking=True)
    def setLockState(self, lock_status):
        """Set the lock state for the VM."""
        ArgumentValidator.validate_integer(lock_status)
        try:
            return self._setLockState(LockStates(lock_status))
        except ValueError:
            raise MCVirtTypeError('Invalid lock state')

    def _setLockState(self, lock_status):
        """Sets the lock status of the VM."""
        # Ensure the user has permission to set VM locks
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SET_VM_LOCK, self)

        # Check if the lock is already set to this state
        if self._getLockState() == lock_status:
            raise VirtualMachineLockException('Lock for \'%s\' is already set to \'%s\'' %
                                              (self.get_name(), self._getLockState().name))

        def update_lock(config):
            """Update lock in VM config."""
            config['lock'] = lock_status.value
        self.get_config_object().update_config(update_lock,
                                               'Setting lock state of \'%s\' to \'%s\'' %
                                               (self.get_name(), lock_status.name))

    @Expose()
    def get_delete_protection_state(self):
        """Get the current state of the deletion lock."""
        return self.get_config_object().get_config()['delete_protection']

    @Expose(locking=True)
    def enable_delete_protection(self):
        """Enable delete protection on the VM."""
        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        # Ensure that delete protection is not already enabled
        if self.get_delete_protection_state():
            raise DeleteProtectionAlreadyEnabledError('Delete protection is already enabled')

        self.update_vm_config(
            change_dict={'delete_protection': True},
            reason='Enable deletion protection',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def disable_delete_protection(self, confirmation):
        """Disable the deletion protection."""
        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        # Check the confirmation is valid (the reverse of the name)
        if confirmation != self.get_name()[::-1]:
            raise InvalidConfirmationCodeError('Invalid confirmation code')

        # Ensure that delete protection is not already enabled
        if not self.get_delete_protection_state():
            raise DeleteProtectionNotEnabledError('Delete protection is already enabled')

        self.update_vm_config(
            change_dict={'delete_protection': False},
            reason='Disable deletion protection',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

    def set_boot_order(self, boot_devices):
        """Sets the boot devices and the order in which devices are booted from."""

        def update_libvirt(domain_xml):
            """Update libvirt config with new boot order."""
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

        self.update_libvirt_config(update_libvirt)

    @Expose(locking=True)
    def update_graphics_driver(self, driver):
        """Update the graphics driver in the libvirt configuration for this VM."""
        # Check the user has permission to modify VMs
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MODIFY_VM, self)

        # Check the provided driver name is valid
        self._get_registered_object('virtual_machine_factory').ensure_graphics_driver_valid(driver)

        if self._is_cluster_master:
            # Update the MCVirt configuration
            self.update_config(['graphics_driver'], driver,
                               'Graphics driver has been changed to %s' % driver)

        if self.isRegisteredRemotely():
            vm_object = self.get_remote_object()
            vm_object.update_graphics_driver(driver)

        elif self.isRegisteredLocally():
            # Ensure VM is unlocked
            self.ensureUnlocked()

            def update_libvirt(domain_xml):
                """Update graphics in libvirt config."""
                domain_xml.find('./devices/video/model').set('type', driver)

            self.update_libvirt_config(update_libvirt)

    def get_graphics_driver(self):
        """Returns the graphics driver for this VM."""
        return self.get_config_object().get_config()['graphics_driver']

    def create_snapshot(self):
        """Create snapshot of the virtual machine."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_VM_SNAPSHOTS, self)

        # If there is a single disk, and the storage backend
        # supports it, then the snapshot can
        # be performed whilst the VM is running.
        # However, if there are multiple disks or the
        # disk cannot handle online snapshotting, then
        # the VM must be stopped.
        hard_disks = self.get_hard_drive_objects()
        if (len(hard_disks) > 1 or
                (hard_disks and
                 not hard_disks[0].supports_online_snapshot)):
            raise VmRunningException(
                'Virtual machine must be stopped before snapshotting.\n'
                'Virtual machine has multiple hard drives and/or'
                ' hard drive storage backend does not support'
                ' online snapshotting.')

    def delete_snapshot(self, snapshot_id):
        """Delete a snapshot."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_VM_SNAPSHOTS, self)

    def revert_snapshot(self, snapshot_id):
        """Revert the state to a snapshot."""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_VM_SNAPSHOTS, self)

        # Virtual machine must be stopped
        if not self.is_stopped:
            raise VmRunningException(
                'Virtual machine must be stopped to revert'
                ' a snapshot')

    def get_sapshots(self):
        """Get virtual machine snapshots."""
        pass

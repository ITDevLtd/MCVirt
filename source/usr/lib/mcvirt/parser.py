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

import argparse
import sys
from mcvirt import MCVirt, MCVirtException
from virtual_machine.virtual_machine import VirtualMachine, LockStates
from virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from virtual_machine.disk_drive import DiskDrive
from virtual_machine.hard_drive.drbd import DrbdVolumeNotInSyncException
from virtual_machine.network_adapter import NetworkAdapter
from node.network import Network
from cluster.cluster import Cluster
from system import System
from node.drbd import DRBD as NodeDRBD
from auth import Auth


class ThrowingArgumentParser(argparse.ArgumentParser):

    """Overrides the ArgumentParser class, in order to change the handling of errors"""

    def error(self, message):
        """Overrides the error function - forcing the argument parser to thrown an MCVirt exception on error"""
        raise MCVirtException(message)


class Parser:

    """Provides an argument parser for MCVirt"""

    def __init__(self, print_status=True):
        """Configures the argument parser object"""
        self.print_status = print_status
        self.parent_parser = ThrowingArgumentParser(add_help=False)

        # Create an argument parser object
        self.parser = ThrowingArgumentParser(description='Manage the MCVirt host')
        self.subparsers = self.parser.add_subparsers(
            dest='action',
            metavar='Action',
            help='Action to perform')

        # Add arguments for starting a VM
        self.start_parser = self.subparsers.add_parser(
            'start',
            help='Start VM help',
            parents=[
                self.parent_parser])
        self.start_parser.add_argument(
            '--iso',
            metavar='ISO Path',
            type=str,
            help='Path of ISO to attach to VM')
        self.start_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        self.start_parser.add_argument(
            '--ignore-drbd',
            dest='ignore_drbd',
            help='Ignores DRBD state',
            action='store_true')

        # Add arguments for stopping a VM
        self.stop_parser = self.subparsers.add_parser(
            'stop',
            help='Stop VM help',
            parents=[
                self.parent_parser])
        self.stop_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Add arguments for creating a VM
        self.create_parser = self.subparsers.add_parser(
            'create',
            help='Create VM help',
            parents=[
                self.parent_parser])
        self.create_parser.add_argument(
            '--memory',
            dest='memory',
            metavar='Memory',
            type=int,
            help='Amount of memory to allocate to the VM (MiB)',
            required=True)
        self.create_parser.add_argument(
            '--disk-size',
            dest='disk_size',
            metavar='Disk Size',
            type=int,
            help='Size of disk to be created for the VM (MB)',
            required=True)
        self.create_parser.add_argument(
            '--cpu-count',
            dest='cpu_count',
            metavar='CPU Count',
            type=int,
            help='Number of virtual CPU cores to be allocated to the VM',
            required=True)
        self.create_parser.add_argument(
            '--network',
            dest='networks',
            metavar='Network Connection',
            type=str,
            action='append',
            help='Name of networks to connect VM to (each network has a separate NIC)')
        self.create_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        # Determine if machine is configured to use DRBD
        hard_drive_storage_types = [n.__name__ for n in HardDriveFactory.getStorageTypes()]
        self.create_parser.add_argument(
            '--storage-type',
            dest='storage_type',
            metavar='Storage backing type',
            type=str,
            choices=hard_drive_storage_types)

        # Get arguments for deleting a VM
        self.delete_parser = self.subparsers.add_parser(
            'delete',
            help='Delete VM help',
            parents=[
                self.parent_parser])
        self.delete_parser.add_argument(
            '--remove-data',
            dest='remove_data',
            help='Removes the VM data from the host',
            action='store_true')
        self.delete_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for updating a VM
        self.update_parser = self.subparsers.add_parser(
            'update',
            help='Update VM help',
            parents=[
                self.parent_parser])
        self.update_parser.add_argument('--memory', dest='memory', metavar='Memory', type=int,
                                        help='Amount of memory to allocate to the VM (MiB)')
        self.update_parser.add_argument(
            '--cpu-count',
            dest='cpu_count',
            metavar='CPU Count',
            type=int,
            help='Number of virtual CPU cores to be allocated to the VM')
        self.update_parser.add_argument(
            '--add-network',
            dest='add_network',
            metavar='Add Network',
            type=str,
            help='Adds a NIC to the VM, connected to the given network')
        self.update_parser.add_argument(
            '--remove-network',
            dest='remove_network',
            metavar='Remove Network',
            type=str,
            help='Removes a NIC from VM with the given MAC-address (e.g. \'00:00:00:00:00:00)\'')
        self.update_parser.add_argument(
            '--add-disk',
            dest='add_disk',
            metavar='Add Disk',
            type=int,
            help='Add disk to the VM (size in MB)')
        hard_drive_storage_types = [n.__name__ for n in HardDriveFactory.getStorageTypes()]
        self.update_parser.add_argument(
            '--storage-type',
            dest='storage_type',
            metavar='Storage backing type',
            type=str,
            choices=hard_drive_storage_types)
        self.update_parser.add_argument(
            '--increase-disk',
            dest='increase_disk',
            metavar='Increase Disk',
            type=int,
            help='Increases VM disk by provided amount (MB)')
        self.update_parser.add_argument('--disk-id', dest='disk_id', metavar='Disk Id', type=int,
                                        help='The ID of the disk to be increased by')
        self.update_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for making permission changes to a VM
        self.permission_parser = self.subparsers.add_parser(
            'permission',
            help='Update VM permissions help',
            parents=[
                self.parent_parser])
        self.permission_parser.add_argument(
            '--add-user',
            dest='add_user',
            metavar='Add User',
            type=str,
            help='Adds a given user to a VM, allowing them to perform basic functions.')
        self.permission_parser.add_argument(
            '--delete-user',
            dest='delete_user',
            metavar='Delete User',
            type=str,
            help='Removes a given user from a VM. This prevents them to perform basic functions.')
        self.permission_parser.add_argument(
            '--add-owner',
            dest='add_owner',
            metavar='Add Owner',
            type=str,
            help='Adds a given user as an owner to a VM, allowing them to perform basic functions and manager users.')
        self.permission_parser.add_argument(
            '--delete-owner',
            dest='delete_owner',
            metavar='Delete User',
            type=str,
            help='Removes a given owner from a VM. This prevents them to perform basic functions and manager users.')
        self.permission_parser.add_argument(
            'vm_name',
            metavar='VM Name',
            type=str,
            help='Name of VM')

        # Create subparser for network-related commands
        self.network_parser = self.subparsers.add_parser(
            'network',
            help='Manage the virtual networks on the MCVirt host',
            parents=[
                self.parent_parser])
        self.network_subparser = self.network_parser.add_subparsers(
            dest='network_action',
            metavar='Action',
            help='Action to perform on the network')
        self.network_create_parser = self.network_subparser.add_parser(
            'create',
            help='Create a network on the MCVirt host')
        self.network_create_parser.add_argument(
            '--interface',
            dest='interface',
            metavar='Interface',
            type=str,
            required=True,
            help='Physical interface on the system to bridge to the virtual network')
        self.network_create_parser.add_argument('network', metavar='Network Name', type=str,
                                                help='Name of the virtual network to be created')
        self.network_delete_parser = self.network_subparser.add_parser(
            'delete',
            help='Delete a network on the MCVirt host')
        self.network_delete_parser.add_argument('network', metavar='Network Name', type=str,
                                                help='Name of the virtual network to be removed')

        # Get arguments for getting VM information
        self.info_parser = self.subparsers.add_parser(
            'info',
            help='View VM info help',
            parents=[
                self.parent_parser])
        self.info_mutually_exclusive_group = self.info_parser.add_mutually_exclusive_group(
            required=False)
        self.info_mutually_exclusive_group.add_argument(
            '--vnc-port',
            dest='vnc_port',
            help='Displays the port that VNC is being hosted from',
            action='store_true')
        self.info_mutually_exclusive_group.add_argument(
            '--node',
            dest='node',
            help='Displays to node that the VM is currently registered on',
            action='store_true')
        self.info_parser.add_argument(
            'vm_name',
            metavar='VM Name',
            type=str,
            help='Name of VM',
            nargs='?',
            default=None)

        # Get arguments for listing VMs
        self.list_parser = self.subparsers.add_parser(
            'list',
            help='List VMs present on host',
            parents=[
                self.parent_parser])

        # Get arguments for cloning a VM
        self.clone_parser = self.subparsers.add_parser(
            'clone',
            help='Clone a VM permissions help',
            parents=[
                self.parent_parser])
        self.clone_parser.add_argument(
            '--template',
            dest='template',
            metavar='Parent VM',
            type=str,
            required=True,
            help='The name of the VM to clone from')
        self.clone_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for cloning a VM
        self.duplicate_parser = self.subparsers.add_parser(
            'duplicate',
            help='Duplicate a VM permissions help',
            parents=[
                self.parent_parser])
        self.duplicate_parser.add_argument(
            '--template',
            dest='template',
            metavar='Parent VM',
            type=str,
            required=True,
            help='The name of the VM to duplicate')
        self.duplicate_parser.add_argument(
            'vm_name',
            metavar='VM Name',
            type=str,
            help='Name of duplicate VM')

        # Get arguments for migrating a VM
        self.migrate_parser = self.subparsers.add_parser(
            'migrate',
            help='Perform migrations of virtual machines',
            parents=[
                self.parent_parser])
        self.migrate_parser.add_argument(
            '--node',
            dest='destination_node',
            metavar='Destination Node',
            type=str,
            required=True,
            help='The name of the destination node for the VM to be migrated to')
        self.migrate_parser.add_argument(
            '--start-after-migration',
            dest='start_after_migration',
            help='Causes the VM to be booted after the migration',
            action='store_true')
        self.migrate_parser.add_argument(
            '--wait-for-shutdown',
            dest='wait_for_shutdown',
            help='Waits for the VM to shutdown before performing the migration',
            action='store_true')
        self.migrate_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create subparser for cluster-related commands
        self.cluster_parser = self.subparsers.add_parser(
            'cluster',
            help='Manage an MCVirt cluster and the connected nodes',
            parents=[
                self.parent_parser])
        self.cluster_subparser = self.cluster_parser.add_subparsers(
            dest='cluster_action',
            metavar='Action',
            help='Action to perform on the cluster')
        self.node_add_parser = self.cluster_subparser.add_parser(
            'add-node',
            help='Adds a node to the MCVirt cluster')
        self.node_add_parser.add_argument(
            '--node',
            dest='node',
            metavar='node',
            type=str,
            required=True,
            help='Hostname of the remote node to add to the cluster')
        self.node_add_parser.add_argument(
            '--ip-address',
            dest='ip_address',
            metavar='IP Address',
            type=str,
            required=True,
            help='Management IP address of the remote node')
        self.node_remove_parser = self.cluster_subparser.add_parser(
            'remove-node',
            help='Removes a node to the MCVirt cluster')
        self.node_remove_parser.add_argument(
            '--node',
            dest='node',
            metavar='node',
            type=str,
            required=True,
            help='Hostname of the remote node to remove from the cluster')

        # Create subparser for VM verification
        self.verify_parser = self.subparsers.add_parser(
            'verify',
            help='Perform verification of VMs',
            parents=[
                self.parent_parser])
        self.verify_mutual_exclusive_group = self.verify_parser.add_mutually_exclusive_group(
            required=True)
        self.verify_mutual_exclusive_group.add_argument(
            '--all',
            dest='all',
            help='Verifies all of the VMs',
            action='store_true')
        self.verify_mutual_exclusive_group.add_argument('vm_name', metavar='VM Name', nargs='?',
                                                        help='Specify a single VM to verify')

        # Create subparser for drbd-related commands
        self.drbd_parser = self.subparsers.add_parser(
            'drbd',
            help='Manage DRBD clustering',
            parents=[
                self.parent_parser])
        self.drbd_parser.add_argument(
            '--enable',
            dest='enable',
            help='Enable DRBD support on the cluster',
            action='store_true')

        # Create subparser for backup commands
        self.backup_parser = self.subparsers.add_parser(
            'backup',
            help='Performs backup-related tasks',
            parents=[
                self.parent_parser])
        self.backup_mutual_exclusive_group = self.backup_parser.add_mutually_exclusive_group(
            required=True)
        self.backup_mutual_exclusive_group.add_argument(
            '--create-snapshot',
            dest='create_snapshot',
            help='Enable DRBD support on the cluster',
            action='store_true')
        self.backup_mutual_exclusive_group.add_argument(
            '--delete-snapshot',
            dest='delete_snapshot',
            help='Enable DRBD support on the cluster',
            action='store_true')
        self.backup_parser.add_argument(
            '--disk-id',
            dest='disk_id',
            metavar='Disk Id',
            type=int,
            required=True,
            help='The ID of the disk to manage the backup snapshot of')
        self.backup_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create subparser for managing VM locks
        self.lock_parser = self.subparsers.add_parser(
            'lock',
            help='Perform verification of VMs',
            parents=[
                self.parent_parser])
        self.lock_mutual_exclusive_group = self.lock_parser.add_mutually_exclusive_group(
            required=True)
        self.lock_mutual_exclusive_group.add_argument(
            '--check-lock',
            dest='check_lock',
            help='Checks the lock status of a VM',
            action='store_true')
        self.lock_mutual_exclusive_group.add_argument(
            '--lock',
            dest='lock',
            help='Locks a VM',
            action='store_true')
        self.lock_mutual_exclusive_group.add_argument(
            '--unlock',
            dest='unlock',
            help='Unlocks a VM',
            action='store_true')
        self.lock_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        self.exit_parser = self.subparsers.add_parser(
            'exit',
            help='Exits the MCVirt shell',
            parents=[
                self.parent_parser])

    def printStatus(self, status):
        """Prints if the user has specified that the parser should
           print statuses"""
        if (self.print_status):
            print status

    def parse_arguments(self, script_args=None, mcvirt_instance=None):
        """Parses arguments and performs actions based on the arguments"""
        # If arguments have been specified, split, so that
        # an array is sent to the argument parser
        if (script_args is not None):
            script_args = script_args.split()

        args = self.parser.parse_args(script_args)
        action = args.action

        # Get an instance of MCVirt
        if (mcvirt_instance is None):
            # Add corner-case to allow host info command to not start
            # the MCVirt object, so that it can view the status of nodes in the cluster
            if not (action == 'info' and args.vm_name is None):
                mcvirt_instance = MCVirt()

        try:
            # Perform functions on the VM based on the action passed to the script
            if (action == 'start'):
                # If the user has specified to ignore DRBD, set the global parameter
                if (args.ignore_drbd):
                    NodeDRBD.ignoreDrbd(mcvirt_instance)

                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                vm_object.start(args.iso if args.iso else None)
                self.printStatus('Successfully started VM')

            elif (action == 'stop'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                vm_object.stop()
                self.printStatus('Successfully stopped VM')

            elif (action == 'create'):
                if (args.storage_type):
                    storage_type = args.storage_type
                else:
                    if (NodeDRBD.isEnabled()):
                        self.parser.error('The VM must be configured with a storage type')
                    else:
                        storage_type = None

                # Convert memory allocation from MiB to KiB
                memory_allocation = int(args.memory) * 1024
                VirtualMachine.create(
                    mcvirt_instance=mcvirt_instance,
                    name=args.vm_name,
                    cpu_cores=args.cpu_count,
                    memory_allocation=memory_allocation,
                    hard_drives=[
                        args.disk_size],
                    network_interfaces=args.networks,
                    storage_type=storage_type)

            elif (action == 'delete'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                vm_object.delete(args.remove_data)

            elif (action == 'update'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                if (args.memory):
                    old_ram_allocation = int(vm_object.getRAM()) / 1024
                    new_ram_allocation = int(args.memory) * 1024
                    vm_object.updateRAM(new_ram_allocation)
                    self.printStatus(
                        'RAM allocation will be changed from %sMiB to %sMiB.' %
                        (old_ram_allocation, args.memory))
                if (args.cpu_count):
                    old_cpu_count = vm_object.getCPU()
                    vm_object.updateCPU(args.cpu_count)
                    self.printStatus(
                        'Number of virtual cores will be changed from %s to %s.' %
                        (old_cpu_count, args.cpu_count))
                if (args.remove_network):
                    network_adapter_object = NetworkAdapter(args.remove_network, vm_object)
                    network_adapter_object.delete()
                if (args.add_network):
                    NetworkAdapter.create(vm_object, args.add_network)
                if (args.add_disk):
                    # Determine if the VM has already been configured to use a storage type
                    vm_storage_type = vm_object.getConfigObject().getConfig()['storage_type']

                    # Ensure that if the VM has not been configured to use a storage type, the node is
                    # capable of DRBD backends that the user has specified a storage backend
                    if (NodeDRBD.isEnabled()):
                        if (vm_storage_type):
                            if (args.storage_type):
                                self.parser.error(
                                    'The VM has already been configured with a storage type, it cannot be changed.')
                        else:
                            if (args.storage_type):
                                # If the VM has not been configured to use a storage type, use
                                # the storage type parameter
                                vm_storage_type = args.storage_type
                            else:
                                self.parser.error(
                                    'The VM is not configured with a storage type, --storage-type must be specified')
                    else:
                        # If DRBD is not enabled, assume the default storage type is being used
                        vm_storage_type = HardDriveFactory.DEFAULT_STORAGE_TYPE

                    HardDriveFactory.create(vm_object, args.add_disk, storage_type)
                if (args.increase_disk and args.disk_id):
                    harddrive_object = HardDriveFactory.getObject(vm_object, args.disk_id)
                    harddrive_object.increaseSize(args.increase_disk)

            elif (action == 'permission'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                auth_object = mcvirt_instance.getAuthObject()
                if (args.add_user):
                    auth_object.addUserPermissionGroup(
                        mcvirt_object=mcvirt_instance,
                        permission_group='user',
                        username=args.add_user,
                        vm_object=vm_object)
                    self.printStatus(
                        'Successfully added \'%s\' as \'user\' to VM \'%s\'' %
                        (args.add_user, vm_object.getName()))
                if (args.delete_user):
                    auth_object.deleteUserPermissionGroup(
                        mcvirt_object=mcvirt_instance,
                        permission_group='user',
                        username=args.delete_user,
                        vm_object=vm_object)
                    self.printStatus(
                        'Successfully removed \'%s\' as \'user\' from VM \'%s\'' %
                        (args.delete_user, vm_object.getName()))
                if (args.add_owner):
                    auth_object.addUserPermissionGroup(
                        mcvirt_object=mcvirt_instance,
                        permission_group='owner',
                        username=args.add_owner,
                        vm_object=vm_object)
                    self.printStatus(
                        'Successfully added \'%s\' as \'owner\' to VM \'%s\'' %
                        (args.add_owner, vm_object.getName()))
                if (args.delete_owner):
                    auth_object.deleteUserPermissionGroup(
                        mcvirt_object=mcvirt_instance,
                        permission_group='owner',
                        username=args.delete_owner,
                        vm_object=vm_object)
                    self.printStatus(
                        'Successfully added \'%s\' as \'owner\' from VM \'%s\'' %
                        (args.delete_owner, vm_object.getName()))

            elif (action == 'info'):
                if (not args.vm_name and (args.vnc_port or args.node)):
                    self.parser.error('Must provide a VM Name')
                if (args.vm_name):
                    vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                    if (args.vnc_port):
                        self.printStatus(vm_object.getVncPort())
                    elif (args.node):
                        self.printStatus(vm_object.getNode())
                    else:
                        self.printStatus(vm_object.getInfo())
                else:
                    mcvirt_instance = MCVirt(initialise_nodes=False)
                    mcvirt_instance.printInfo()

            elif (action == 'network'):
                if (args.network_action == 'create'):
                    Network.create(mcvirt_instance, args.network, args.interface)
                elif (args.network_action == 'delete'):
                    network_object = Network(mcvirt_instance, args.network)
                    network_object.delete()

            elif (action == 'migrate'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                vm_object.offlineMigrate(
                    args.destination_node,
                    wait_for_vm_shutdown=args.wait_for_shutdown,
                    start_after_migration=args.start_after_migration)

            elif (action == 'cluster'):
                if (args.cluster_action == 'add-node'):
                    password = System.getUserInput(
                        'Enter \'%s\' root password: ' %
                        args.node, True)
                    cluster_object = Cluster(mcvirt_instance)
                    cluster_object.addNode(args.node, args.ip_address, password)
                    self.printStatus('Successfully added node %s' % args.node)
                if (args.cluster_action == 'remove-node'):
                    cluster_object = Cluster(mcvirt_instance)
                    cluster_object.removeNode(args.node)
                    self.printStatus('Successfully removed node %s' % args.node)

            elif (action == 'verify'):
                if (args.vm_name):
                    vm_objects = [VirtualMachine(mcvirt_instance, args.vm_name)]
                elif (args.all):
                    vm_objects = mcvirt_instance.getAllVirtualMachineObjects()

                # Iterate over the VMs and check each disk
                failures = []
                for vm_object in vm_objects:
                    for disk_object in vm_object.getDiskObjects():
                        if (disk_object.getType() == 'DRBD'):
                            # Catch any exceptions due to the DRBD volume not being in-sync
                            try:
                                disk_object.verify()
                                self.printStatus(
                                    'DRBD verification for %s (%s) completed without out-of-sync blocks' %
                                    (disk_object.getConfigObject()._getResourceName(), vm_object.getName()))
                            except DrbdVolumeNotInSyncException as e:
                                # Append the not-in-sync exception message to an array, so the rest of the
                                # disks can continue to be checked
                                failures.append(e.message)

                # If there were any failures during the verification, raise the exception and print
                # all exception messages
                if (failures):
                    raise DrbdVolumeNotInSyncException("\n".join(failures))

            elif (action == 'drbd'):
                if (args.enable):
                    DRBD.enable(mcvirt_instance)

            elif (action == 'backup'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                hard_drive_object = HardDriveFactory.getObject(vm_object, args.disk_id)
                if (args.create_snapshot):
                    self.printStatus(hard_drive_object.createBackupSnapshot())
                elif (args.delete_snapshot):
                    hard_drive_object.deleteBackupSnapshot()

            elif (action == 'lock'):
                vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
                if (args.lock):
                    vm_object.setLockState(LockStates(LockStates.LOCKED))
                if (args.unlock):
                    vm_object.setLockState(LockStates(LockStates.UNLOCKED))
                if (args.check_lock):
                    self.printStatus(LockStates(vm_object.getLockState()).name)

            elif (action == 'clone'):
                vm_object = VirtualMachine(mcvirt_instance, args.template)
                vm_object.clone(mcvirt_instance, args.vm_name)

            elif (action == 'duplicate'):
                vm_object = VirtualMachine(mcvirt_instance, args.template)
                vm_object.duplicate(mcvirt_instance, args.vm_name)

            elif (action == 'list'):
                mcvirt_instance.listVms()
        except Exception as e:
            # Unset mcvirt instance - forcing the object to be destroyed
            raise Exception, e, sys.exc_info()[2]

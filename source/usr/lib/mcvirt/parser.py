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

from mcvirt import MCVirt
from exceptions import ArgumentParserException, DrbdVolumeNotInSyncException
from virtual_machine.virtual_machine import VirtualMachine, LockStates
from virtual_machine.hard_drive.config.base import (Base as HardDriveConfigBase,
                                                    Driver as HardDriveDriver)
from virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from virtual_machine.network_adapter import NetworkAdapter
from virtual_machine.disk_drive import DiskDrive
from node.network.network import Network
from cluster.cluster import Cluster
from system import System
from node.drbd import DRBD as NodeDRBD
from node.node import Node
from auth.auth import Auth
from client.rpc import Connection
from iso.iso import Iso


class ThrowingArgumentParser(argparse.ArgumentParser):
    """Overrides the ArgumentParser class, in order to change the handling of errors"""

    def error(self, message):
        """Overrides the error function - forcing the argument parser to throw
        an MCVirt exception on error
        """
        raise ArgumentParserException(message)


class Parser:
    """Provides an argument parser for MCVirt"""

    SESSION_ID = None
    USERNAME = None

    def __init__(self, print_status=True, auth_object=None):
        """Configures the argument parser object"""
        self.print_status = print_status
        self.parent_parser = ThrowingArgumentParser(add_help=False)

        self.parent_parser.add_argument('--username', '-U', dest='username',
                                        help='MCVirt username')
        self.parent_parser.add_argument('--password', dest='password',
                                        help='MCVirt password')
        self.parent_parser.add_argument('--ignore-failed-nodes', dest='ignore_failed_nodes',
                                        help='Ignores nodes that are inaccessible',
                                        action='store_true')
        self.parent_parser.add_argument('--accept-failed-nodes-warning',
                                        dest='accept_failed_nodes_warning',
                                        help=argparse.SUPPRESS, action='store_true')
        self.parent_parser.add_argument('--ignore-drbd', dest='ignore_drbd',
                                        help='Ignores DRBD state', action='store_true')

        argparser_description = "\nMCVirt - Managed Consistent Virtualisation\n\n" + \
                                'Manage the MCVirt host'
        argparser_epilog = "\nFor more information, see http://mcvirt.itdev.co.uk\n"

        # Create an argument parser object
        self.parser = ThrowingArgumentParser(description=argparser_description,
                                             epilog=argparser_epilog,
                                             formatter_class=argparse.RawDescriptionHelpFormatter)
        self.subparsers = self.parser.add_subparsers(dest='action', metavar='Action',
                                                     help='Action to perform')

        # Add arguments for starting a VM
        self.start_parser = self.subparsers.add_parser('start', help='Start VM',
                                                       parents=[self.parent_parser])
        self.start_parser.add_argument('--iso', metavar='ISO Name', type=str,
                                       help='Path of ISO to attach to VM')
        self.start_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Add arguments for stopping a VM
        self.stop_parser = self.subparsers.add_parser('stop', help='Stop VM',
                                                      parents=[self.parent_parser])
        self.stop_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Add arguments for resetting a VM
        self.reset_parser = self.subparsers.add_parser('reset', help='Reset VM',
                                                       parents=[self.parent_parser])
        self.reset_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Add arguments for ISO functions
        self.iso_parser = self.subparsers.add_parser('iso', help='ISO managment',
                                                     parents=[self.parent_parser])
        self.iso_parser.add_argument('--list', dest='list', action='store_true',
                                     help='List available ISOs')
        self.iso_parser.add_argument('--add-from-path', dest='add_path',
                                     help='Copy an ISO to ISO directory', metavar='PATH')
        self.iso_parser.add_argument('--delete', dest='delete_path', help='Delete an ISO',
                                     metavar='NAME')
        self.iso_parser.add_argument('--add-from-url', dest='add_url',
                                     help='Download and add an ISO', metavar='URL')

        # Add arguments for creating a VM
        self.create_parser = self.subparsers.add_parser('create', help='Create VM',
                                                        parents=[self.parent_parser])
        self.create_parser.add_argument('--memory', dest='memory', metavar='Memory',
                                        required=True, type=int,
                                        help='Amount of memory to allocate to the VM (MiB)')
        self.create_parser.add_argument('--disk-size', dest='disk_size', metavar='Disk Size',
                                        type=int, required=True,
                                        help='Size of disk to be created for the VM (MB)')
        self.create_parser.add_argument(
            '--cpu-count', dest='cpu_count', metavar='CPU Count',
            help='Number of virtual CPU cores to be allocated to the VM',
            type=int, required=True
        )
        self.create_parser.add_argument(
            '--network', dest='networks', metavar='Network Connection',
            type=str, action='append',
            help='Name of networks to connect VM to (each network has a separate NIC)'
        )
        self.create_parser.add_argument('--nodes', dest='nodes', action='append',
                                        help='Specify the nodes that the VM will be' +
                                             ' hosted on, if a DRBD storage-type' +
                                             ' is specified',
                                        default=[])

        self.create_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        # Determine if machine is configured to use DRBD
        hard_drive_storage_types = [n.__name__ for n in HardDriveFactory.getStorageTypes()]
        self.create_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type',
                                        type=str, default=None, choices=hard_drive_storage_types)
        self.create_parser.add_argument('--driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)

        # Get arguments for deleting a VM
        self.delete_parser = self.subparsers.add_parser('delete', help='Delete VM',
                                                        parents=[self.parent_parser])
        self.delete_parser.add_argument('--remove-data', dest='remove_data', action='store_true',
                                        help='Removes the VM data from the host')
        self.delete_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for registering a VM
        self.register_parser = self.subparsers.add_parser('register', help='Registers a VM on' +
                                                                           ' the local node',
                                                          parents=[self.parent_parser])
        self.register_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for unregistering a VM
        self.unregister_parser = self.subparsers.add_parser('unregister',
                                                            help='Unregisters a VM from' +
                                                                 ' the local node',
                                                            parents=[self.parent_parser])
        self.unregister_parser.add_argument('vm_name', metavar='VM Name', type=str,
                                            help='Name of VM')

        # Get arguments for updating a VM
        self.update_parser = self.subparsers.add_parser('update', help='Update VM Configuration',
                                                        parents=[self.parent_parser])
        self.update_parser.add_argument('--memory', dest='memory', metavar='Memory', type=int,
                                        help='Amount of memory to allocate to the VM (MiB)')
        self.update_parser.add_argument(
            '--cpu-count', dest='cpu_count', metavar='CPU Count', type=int,
            help='Number of virtual CPU cores to be allocated to the VM'
        )
        self.update_parser.add_argument(
            '--add-network',
            dest='add_network',
            metavar='Add Network',
            type=str,
            help='Adds a NIC to the VM, connected to the given network'
        )
        self.update_parser.add_argument(
            '--remove-network',
            dest='remove_network',
            metavar='Remove Network',
            type=str,
            help='Removes a NIC from VM with the given MAC-address (e.g. \'00:00:00:00:00:00)\''
        )
        self.update_parser.add_argument('--add-disk', dest='add_disk', metavar='Add Disk',
                                        type=int, help='Add disk to the VM (size in MB)')
        self.update_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type', type=str,
                                        default=None)
        self.update_parser.add_argument('--driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)
        self.update_parser.add_argument('--increase-disk', dest='increase_disk',
                                        metavar='Increase Disk', type=int,
                                        help='Increases VM disk by provided amount (MB)')
        self.update_parser.add_argument('--disk-id', dest='disk_id', metavar='Disk Id', type=int,
                                        help='The ID of the disk to be increased by')
        self.update_parser.add_argument('--attach-iso', '--iso', dest='iso', metavar='ISO Name',
                                        type=str,
                                        help=('Attach an ISO to a running VM.'
                                              ' Specify without value to detach ISO.'))
        self.update_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for making permission changes to a VM
        self.permission_parser = self.subparsers.add_parser(
            'permission',
            help='Update user permissions',
            parents=[self.parent_parser]
        )
        self.permission_parser.add_argument(
            '--add-user',
            dest='add_user',
            metavar='Add user to user group',
            type=str,
            help='Adds a given user to a VM, allowing them to perform basic functions.'
        )
        self.permission_parser.add_argument(
            '--delete-user',
            dest='delete_user',
            metavar='Remove user from user group',
            type=str,
            help='Removes a given user from a VM. This prevents them to perform basic functions.'
        )
        self.permission_parser.add_argument(
            '--add-owner',
            dest='add_owner',
            metavar='Add user to owner group',
            type=str,
            help=('Adds a given user as an owner to a VM, '
                  'allowing them to perform basic functions and manager users.')
        )
        self.permission_parser.add_argument(
            '--delete-owner',
            dest='delete_owner',
            metavar='Remove user from owner group',
            type=str,
            help=('Removes a given owner from a VM. '
                  'This prevents them to perform basic functions and manager users.')
        )
        self.permission_parser.add_argument(
            '--add-superuser',
            dest='add_superuser',
            metavar='Add user to superuser group',
            type=str,
            help=('Adds a given user to the global superuser role. '
                  'This allows the user to completely manage the MCVirt node/cluster')
        )
        self.permission_parser.add_argument(
            '--delete-superuser',
            dest='delete_superuser',
            metavar='Removes user from the superuser group',
            type=str,
            help='Removes a given user from the superuser group'
        )
        self.permission_target_group = self.permission_parser.add_mutually_exclusive_group(
            required=True
        )
        self.permission_target_group.add_argument('vm_name', metavar='VM Name',
                                                  type=str, help='Name of VM', nargs='?')
        self.permission_target_group.add_argument('--global', dest='global', action='store_true',
                                                  help='Set a global MCVirt permission')

        # Create subparser for network-related commands
        self.network_parser = self.subparsers.add_parser(
            'network',
            help='Manage the virtual networks on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.network_subparser = self.network_parser.add_subparsers(
            dest='network_action',
            metavar='Action',
            help='Action to perform on the network'
        )
        self.network_create_parser = self.network_subparser.add_parser(
            'create',
            help='Create a network on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.network_create_parser.add_argument(
            '--interface',
            dest='interface',
            metavar='Interface',
            type=str,
            required=True,
            help='Physical interface on the system to bridge to the virtual network'
        )
        self.network_create_parser.add_argument('network', metavar='Network Name', type=str,
                                                help='Name of the virtual network to be created')
        self.network_delete_parser = self.network_subparser.add_parser(
            'delete',
            help='Delete a network on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.network_delete_parser.add_argument('network', metavar='Network Name', type=str,
                                                help='Name of the virtual network to be removed')
        self.network_subparser.add_parser('list', help='List the networks on the node',
                                          parents=[self.parent_parser])

        # Get arguments for getting VM information
        self.info_parser = self.subparsers.add_parser('info', help='View VM information',
                                                      parents=[self.parent_parser])
        self.info_mutually_exclusive_group = self.info_parser.add_mutually_exclusive_group(
            required=False
        )
        self.info_mutually_exclusive_group.add_argument(
            '--vnc-port',
            dest='vnc_port',
            help='Displays the port that VNC is being hosted from',
            action='store_true'
        )
        self.info_mutually_exclusive_group.add_argument(
            '--node',
            dest='node',
            help='Displays which node that the VM is currently registered on',
            action='store_true'
        )
        self.info_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM',
                                      nargs='?', default=None)

        # Get arguments for listing VMs
        self.list_parser = self.subparsers.add_parser('list', help='List VMs present on host',
                                                      parents=[self.parent_parser])

        # Get arguments for cloning a VM
        self.clone_parser = self.subparsers.add_parser('clone', help='Clone a VM',
                                                       parents=[self.parent_parser])
        self.clone_parser.add_argument('--template', dest='template', type=str,
                                       required=True, metavar='Parent VM',
                                       help='The name of the VM to clone from')
        self.clone_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for cloning a VM
        self.duplicate_parser = self.subparsers.add_parser('duplicate',
                                                           help='Duplicate a VM',
                                                           parents=[self.parent_parser])
        self.duplicate_parser.add_argument('--template', dest='template', metavar='Parent VM',
                                           type=str, required=True,
                                           help='The name of the VM to duplicate')
        self.duplicate_parser.add_argument('vm_name', metavar='VM Name', type=str,
                                           help='Name of duplicate VM')

        # Get arguments for migrating a VM
        self.migrate_parser = self.subparsers.add_parser(
            'migrate',
            help='Perform migrations of virtual machines',
            parents=[self.parent_parser]
        )
        self.migrate_parser.add_argument(
            '--node',
            dest='destination_node',
            metavar='Destination Node',
            type=str,
            required=True,
            help='The name of the destination node for the VM to be migrated to'
        )
        self.migrate_parser.add_argument(
            '--online',
            dest='online_migration',
            help='Perform an online-migration',
            action='store_true'
        )
        self.migrate_parser.add_argument(
            '--start-after-migration',
            dest='start_after_migration',
            help='Causes the VM to be booted after the migration',
            action='store_true'
        )
        self.migrate_parser.add_argument(
            '--wait-for-shutdown',
            dest='wait_for_shutdown',
            help='Waits for the VM to shutdown before performing the migration',
            action='store_true'
        )
        self.migrate_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create sub-parser for moving VMs
        self.move_parser = self.subparsers.add_parser('move', help='Move a VM and related storage' +
                                                                   ' to another node',
                                                      parents=[self.parent_parser])
        self.move_parser.add_argument('--source-node', dest='source_node',
                                      help="The node that the VM will be moved from.\n" +
                                      'For DRBD VMs, the source node must not be' +
                                      " the local node.\nFor Local VMs, the node" +
                                      " must be the local node, but may be omitted.")
        self.move_parser.add_argument('--destination-node', dest='destination_node',
                                      help='The node that the VM will be moved to')
        self.move_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create subparser for cluster-related commands
        self.cluster_parser = self.subparsers.add_parser(
            'cluster',
            help='Manage an MCVirt cluster and the connected nodes',
            parents=[self.parent_parser]
        )
        self.cluster_subparser = self.cluster_parser.add_subparsers(
            dest='cluster_action',
            metavar='Action',
            help='Action to perform on the cluster'
        )
        self.connection_string_subparser = self.cluster_subparser.add_parser(
            'get-connect-string',
            help='Generates a connection string to add the node to a cluster',
            parents=[self.parent_parser]
        )
        self.node_add_parser = self.cluster_subparser.add_parser(
            'add-node',
            help='Adds a node to the MCVirt cluster',
            parents=[self.parent_parser])
        self.node_add_parser.add_argument(
            '--connect-string',
            dest='connect_string',
            metavar='node',
            type=str,
            required=True,
            help='Connect string from the target node')
        self.node_remove_parser = self.cluster_subparser.add_parser(
            'remove-node',
            help='Removes a node to the MCVirt cluster',
            parents=[self.parent_parser]
        )
        self.node_remove_parser.add_argument(
            '--node',
            dest='node',
            metavar='node',
            type=str,
            required=True,
            help='Hostname of the remote node to remove from the cluster')

        # Create subparser for commands relating to the local node configuration
        self.node_parser = self.subparsers.add_parser(
            'node',
            help='Modify configurations relating to the local node',
            parents=[self.parent_parser]
        )
        self.node_parser.add_argument('--set-vm-vg', dest='volume_group', metavar='VM Volume Group',
                                      help=('Sets the local volume group used for Virtual'
                                            ' machine HDD logical volumes'))
        self.node_parser.add_argument('--set-ip-address', dest='ip_address',
                                      metavar='Cluster IP Address',
                                      help=('Sets the cluster IP address for the local node,'
                                            ' used for DRBD and cluster management.'))

        # Create subparser for VM verification
        self.verify_parser = self.subparsers.add_parser(
            'verify',
            help='Perform verification of VMs',
            parents=[
                self.parent_parser])
        self.verify_mutual_exclusive_group = self.verify_parser.add_mutually_exclusive_group(
            required=True
        )
        self.verify_mutual_exclusive_group.add_argument('--all', dest='all', action='store_true',
                                                        help='Verifies all of the VMs')
        self.verify_mutual_exclusive_group.add_argument('vm_name', metavar='VM Name', nargs='?',
                                                        help='Specify a single VM to verify')

        # Create subparser for drbd-related commands
        self.drbd_parser = self.subparsers.add_parser('drbd', help='Manage DRBD clustering',
                                                      parents=[self.parent_parser])
        self.drbd_mutually_exclusive_group = self.drbd_parser.add_mutually_exclusive_group(
            required=True
        )
        self.drbd_mutually_exclusive_group.add_argument(
            '--enable', dest='enable', action='store_true',
            help='Enable DRBD support on the cluster'
        )
        self.drbd_mutually_exclusive_group.add_argument(
            '--list', dest='list', action='store_true',
            help='List DRBD volumes on the system'
        )

        # Create subparser for backup commands
        self.backup_parser = self.subparsers.add_parser('backup',
                                                        help='Performs backup-related tasks',
                                                        parents=[self.parent_parser])
        self.backup_mutual_exclusive_group = self.backup_parser.add_mutually_exclusive_group(
            required=True
        )
        self.backup_mutual_exclusive_group.add_argument(
            '--create-snapshot',
            dest='create_snapshot',
            help='Enable DRBD support on the cluster',
            action='store_true'
        )
        self.backup_mutual_exclusive_group.add_argument(
            '--delete-snapshot',
            dest='delete_snapshot',
            help='Enable DRBD support on the cluster',
            action='store_true'
        )
        self.backup_parser.add_argument(
            '--disk-id',
            dest='disk_id',
            metavar='Disk Id',
            type=int,
            required=True,
            help='The ID of the disk to manage the backup snapshot of'
        )
        self.backup_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create subparser for managing VM locks
        self.lock_parser = self.subparsers.add_parser('lock', help='Perform verification of VMs',
                                                      parents=[self.parent_parser])
        self.lock_mutual_exclusive_group = self.lock_parser.add_mutually_exclusive_group(
            required=True
        )
        self.lock_mutual_exclusive_group.add_argument('--check-lock', dest='check_lock',
                                                      help='Checks the lock status of a VM',
                                                      action='store_true')
        self.lock_mutual_exclusive_group.add_argument('--lock', dest='lock', help='Locks a VM',
                                                      action='store_true')
        self.lock_mutual_exclusive_group.add_argument('--unlock', dest='unlock',
                                                      help='Unlocks a VM', action='store_true')
        self.lock_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        self.exit_parser = self.subparsers.add_parser('exit', help='Exits the MCVirt shell',
                                                      parents=[self.parent_parser])

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

        # Obtain connection to Pyro server
        if Parser.SESSION_ID and Parser.USERNAME:
            rpc = Connection(username=Parser.USERNAME, session_id=Parser.SESSION_ID)
        else:
            # Check if user/password have been passed. Else, ask for them.
            username = args.username if args.username else System.getUserInput('Username: ').rstrip()
            password = args.password if args.password else System.getUserInput('Password: ',
                                                                               password=True).rstrip()
            rpc = Connection(username=username, password=password)
            Parser.SESSION_ID = rpc.SESSION_ID
            Parser.USERNAME = username


        if args.ignore_failed_nodes:
            # If the user has specified to ignore the cluster,
            # print a warning and confirm the user's answer
            if (not args.accept_failed_nodes_warning):
                self.printStatus('WARNING: Running MCVirt with --ignore-failed-nodes' +
                                 ' can leave the cluster in an inconsistent state!')
                continue_answer = System.getUserInput('Would you like to continue? (Y/n): ')

                if (continue_answer.strip() is not 'Y'):
                    self.printStatus('Cancelled...')
                    return
            ignore_failed_nodes = True
        else:
            ignore_failed_nodes = False

        # Perform functions on the VM based on the action passed to the script
        if action == 'start':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)

            if args.iso:
                iso_factory = rpc.getConnection('iso_factory')
                iso_object = iso_factory.getIsoByName(args.iso)
                rpc.annotateObject(iso_object)
            else:
                iso_object = None
            vm_object.start(iso_object=iso_object)
            self.printStatus('Successfully started VM')

        elif action == 'stop':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)
            vm_object.stop()
            self.printStatus('Successfully stopped VM')

        elif action == 'reset':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)
            vm_object.reset()
            self.printStatus('Successfully reset VM')

        elif action == 'create':
            storage_type = args.storage_type or None

            # Convert memory allocation from MiB to KiB
            memory_allocation = int(args.memory) * 1024
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.create(
                name=args.vm_name,
                cpu_cores=args.cpu_count,
                memory_allocation=memory_allocation,
                hard_drives=[args.disk_size],
                network_interfaces=args.networks,
                storage_type=storage_type,
                hard_drive_driver=args.hard_disk_driver,
                available_nodes=args.nodes)

        elif action == 'delete':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)
            vm_object.delete(args.remove_data)

        elif action == 'register':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)
            vm_object.register()

        elif action == 'unregister':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)
            vm_object.unregister()

        elif action == 'update':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotateObject(vm_object)

            if args.memory:
                old_ram_allocation_kib = vm_object.getRAM()
                old_ram_allocation = int(old_ram_allocation_kib) / 1024
                new_ram_allocation = int(args.memory) * 1024
                vm_object.updateRAM(new_ram_allocation, old_value=old_ram_allocation_kib)
                self.printStatus(
                    'RAM allocation will be changed from %sMiB to %sMiB.' %
                    (old_ram_allocation, args.memory)
                )

            if args.cpu_count:
                old_cpu_count = vm_object.getCPU()
                vm_object.updateCPU(args.cpu_count, old_value=old_cpu_count)
                self.printStatus(
                    'Number of virtual cores will be changed from %s to %s.' %
                    (old_cpu_count, args.cpu_count)
                )

            if args.remove_network:
                network_adapter_object = vm_object.getNetworkAdapterByMacAdress(args.remove_network)
                rpc.annotateObject(network_adapter_object)
                network_adapter_object.delete()

            if (args.add_network):
                network_factory = rpc.getConnection('network_factory')
                network_object = network_factory.getNetworkByName(args.add_network)
                rpc.annotateObject(network_object)
                vm_object.createNetworkAdapter(network_object)

            if args.add_disk:
                hard_drive_factory = rpc.getConnection('hard_drive_factory')
                hard_drive_factory.create(vm_object, size=args.add_disk,
                                        storage_type=args.storage_type,
                                        driver=args.hard_disk_driver)

            if (args.increase_disk and args.disk_id):
                hard_drive_factory = rpc.getConnection('hard_drive_factory')
                hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
                rpc.annotateObject(hard_drive_object)
                hard_drive_object.increaseSize(args.increase_disk)

            if args.iso:
                iso_factory = rpc.getConnection('iso_factory')
                iso_object = iso_factory.getIsoByName(args.iso)
                rpc.annotateObject(iso_object)
                disk_drive = vm_object.get_disk_drive()
                rpc.annotateObject(disk_drive)
                disk_drive.attachISO(iso_object, True)

        elif action == 'permission':
            if (args.add_superuser or args.delete_superuser) and args.vm_name:
                raise ArgumentParserException('Superuser groups are global-only roles')

            if args.vm_name:
                vm_factory = rpc.getConnection('virtual_machine_factory')
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                rpc.annotateObject(vm_object)
                permission_destination_string = 'role on VM %s' % vm_object.getName()
            else:
                vm_object = None
                permission_destination_string = 'global role'

            auth_object = rpc.getConnection('auth')
            rpc.annotateObject(auth_object)
            user_factory = rpc.getConnection('user_factory')
            rpc.annotateObject(user_factory)

            if args.add_user:
                user_object = user_factory.get_user_by_username(args.add_user)
                rpc.annotateObject(user_object)
                auth_object.addUserPermissionGroup(
                    permission_group='user',
                    user_object=user_object,
                    vm_object=vm_object)
                self.printStatus(
                    'Successfully added \'%s\' to \'user\' %s' %
                    (args.add_user, permission_destination_string))

            if args.delete_user:
                user_object = user_factory.get_user_by_username(args.delete_user)
                rpc.annotateObject(user_object)
                auth_object.deleteUserPermissionGroup(
                    permission_group='user',
                    user_object=user_object,
                    vm_object=vm_object)
                self.printStatus(
                    'Successfully removed \'%s\' from \'user\' %s' %
                    (args.delete_user, permission_destination_string))

            if args.add_owner:
                user_object = user_factory.get_user_by_username(args.add_owner)
                rpc.annotateObject(user_object)
                auth_object.addUserPermissionGroup(
                    permission_group='owner',
                    user_object=user_object,
                    vm_object=vm_object)
                self.printStatus(
                    'Successfully added \'%s\' to \'owner\' %s' %
                    (args.add_owner, permission_destination_string))

            if args.delete_owner:
                user_object = user_factory.get_user_by_username(args.delete_owner)
                rpc.annotateObject(user_object)
                auth_object.deleteUserPermissionGroup(
                    permission_group='owner',
                    user_object=user_object,
                    vm_object=vm_object)
                self.printStatus(
                    'Successfully removed \'%s\' from \'owner\' %s' %
                    (args.delete_owner, permission_destination_string))

            if args.add_superuser:
                user_object = user_factory.get_user_by_username(args.add_superuser)
                rpc.annotateObject(user_object)
                auth_object.addSuperuser(user_object=user_object)
                self.printStatus('Successfully added %s to the global superuser group' %
                                 args.add_superuser)
            if args.delete_superuser:
                user_object = user_factory.get_user_by_username(args.delete_superuser)
                rpc.annotateObject(user_object)
                auth_object.deleteSuperuser(user_object=user_object)
                self.printStatus('Successfully removed %s from the global superuser group ' %
                                 args.delete_superuser)

        elif action == 'info':
            if not args.vm_name and (args.vnc_port or args.node):
                self.parser.error('Must provide a VM Name')
            if args.vm_name:
                vm_factory = rpc.getConnection('virtual_machine_factory')
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                rpc.annotateObject(vm_object)
                if (args.vnc_port):
                    self.printStatus(vm_object.getVncPort())
                elif args.node:
                    self.printStatus(vm_object.getNode())
                else:
                    self.printStatus(vm_object.getInfo())
            else:
                cluster_object = rpc.getConnection('cluster')
                self.printStatus(cluster_object.printInfo())

        elif action == 'network':
            network_factory = rpc.getConnection('network_factory')
            if args.network_action == 'create':
                network_factory.create(args.network, physical_interface=args.interface)
            elif args.network_action == 'delete':
                network_object = network_factory.getNetworkByName(args.network)
                rpc.annotateObject(network_object)
                network_object.delete()
            elif args.network_action == 'list':
                self.printStatus(network_factory.getNetworkListTable())

        elif (action == 'migrate'):
            vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
            if (args.online_migration):
                vm_object.onlineMigrate(args.destination_node)
            else:
                vm_object.offlineMigrate(
                    args.destination_node,
                    wait_for_vm_shutdown=args.wait_for_shutdown,
                    start_after_migration=args.start_after_migration)
            self.printStatus('Successfully migrated \'%s\' to %s' %
                             (vm_object.getName(), args.destination_node))

        elif (action == 'move'):
            vm_object = VirtualMachine(mcvirt_instance, args.vm_name)
            vm_object.move(destination_node=args.destination_node,
                           source_node=args.source_node)

        elif (action == 'cluster'):
            if args.cluster_action == 'get-connect-string':
                cluster_object = rpc.getConnection('cluster')
                self.printStatus(cluster_object.getConnectionString())
            if (args.cluster_action == 'add-node'):
                cluster_object = rpc.getConnection('cluster')
                if args.connect_string:
                    connect_string = args.connect_string
                else:
                    connect_string = System.getUserInput('Enter Connect String: ')
                cluster_object.addNode(connect_string)
                self.printStatus('Successfully added node')
            if (args.cluster_action == 'remove-node'):
                cluster_object = Cluster(mcvirt_instance)
                cluster_object.removeNode(args.node)
                self.printStatus('Successfully removed node %s' % args.node)

        elif (action == 'node'):
            if (args.volume_group):
                Node.setStorageVolumeGroup(mcvirt_instance, args.volume_group)
                self.printStatus('Successfully set VM storage volume group to %s' %
                                 args.volume_group)

            if (args.ip_address):
                Node.setClusterIpAddress(mcvirt_instance, args.ip_address)
                self.printStatus('Successfully set cluster IP address to %s' % args.ip_address)

        elif (action == 'verify'):
            if (args.vm_name):
                vm_objects = [VirtualMachine(mcvirt_instance, args.vm_name)]
            elif (args.all):
                vm_objects = mcvirt_instance.getAllVirtualMachineObjects()

            # Iterate over the VMs and check each disk
            failures = []
            for vm_object in vm_objects:
                for disk_object in vm_object.getHardDriveObjects():
                    if (disk_object.getType() == 'DRBD'):
                        # Catch any exceptions due to the DRBD volume not being in-sync
                        try:
                            disk_object.verify()
                            self.printStatus(
                                ('DRBD verification for %s (%s) completed '
                                 'without out-of-sync blocks') %
                                (disk_object.getConfigObject()._getResourceName(),
                                 vm_object.getName())
                            )
                        except DrbdVolumeNotInSyncException, e:
                            # Append the not-in-sync exception message to an array,
                            # so the rest of the disks can continue to be checked
                            failures.append(e.message)

            # If there were any failures during the verification, raise the exception and print
            # all exception messages
            if (failures):
                raise DrbdVolumeNotInSyncException("\n".join(failures))

        elif (action == 'drbd'):
            if (args.enable):
                NodeDRBD.enable(mcvirt_instance)
            if (args.list):
                self.printStatus(NodeDRBD.list(mcvirt_instance))

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

        elif action == 'list':
            vm_factory = rpc.getConnection('virtual_machine_factory')
            self.printStatus(vm_factory.listVms())

        elif action == 'iso':
            iso_factory = rpc.getConnection('iso_factory')
            if args.list:
                iso_factory = rpc.getConnection('iso_factory')
                self.printStatus(iso_factory.getIsoList())

            # Tempoarrily disabled until it is determined how this will work
            # if (args.add_path):
            #     iso_object = Iso.addIso(mcvirt_instance, args.add_path)
            #     self.printStatus('Successfully added ISO: %s' % iso_object.getName())

            if args.delete_path:
                iso_object = iso_factory.getIsoByName(args.delete_path)
                rpc.annotateObject(iso_object)
                iso_object.delete()
                self.printStatus('Successfully removed iso: %s' % args.delete_path)

            if (args.add_url):
                iso_object = iso_factory.addFromUrl(mcvirt_instance, args.add_url)
                self.printStatus('Successfully added ISO: %s' % iso_object.getName())

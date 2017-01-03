"""Provides argument parser."""

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
import binascii
import os

from mcvirt.exceptions import (ArgumentParserException, DrbdVolumeNotInSyncException,
                               AuthenticationError)
from mcvirt.client.rpc import Connection
from mcvirt.system import System
from mcvirt.constants import LockStates
from mcvirt.auth.user_types.user_base import UserBase


class ThrowingArgumentParser(argparse.ArgumentParser):
    """Override the ArgumentParser class, in order to change the handling of errors."""

    def error(self, message):
        """Override the error function."""
        # Force the argument parser to throw an MCVirt exception on error.
        raise ArgumentParserException(message)


class Parser(object):
    """Provides an argument parser for MCVirt."""

    AUTH_FILE = '.mcvirt-auth'

    def __init__(self, verbose=True):
        """Configure the argument parser object."""
        self.USERNAME = None
        self.SESSION_ID = None
        self.verbose = verbose
        self.parent_parser = ThrowingArgumentParser(add_help=False)

        self.parent_parser.add_argument('--username', '-U', dest='username',
                                        help='MCVirt username')
        self.parent_parser.add_argument('--password', dest='password',
                                        help='MCVirt password')
        self.parent_parser.add_argument('--cache-credentials', dest='cache_credentials',
                                        action='store_true',
                                        help=('Store the session ID, so it can be used for '
                                              'multiple MCVirt calls.'))
        self.parent_parser.add_argument('--ignore-failed-nodes', dest='ignore_failed_nodes',
                                        help='Ignores nodes that are inaccessible',
                                        action='store_true')
        self.parent_parser.add_argument('--accept-failed-nodes-warning',
                                        dest='accept_failed_nodes_warning',
                                        help=argparse.SUPPRESS, action='store_true')
        self.parent_parser.add_argument('--ignore-drbd', dest='ignore_drbd',
                                        help='Ignores Drbd state', action='store_true')

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
                                       help='Path of ISO to attach to VM', default=None)
        self.start_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                       help='Names of VMs')

        # Add arguments for stopping a VM
        self.stop_parser = self.subparsers.add_parser('stop', help='Stop VM',
                                                      parents=[self.parent_parser])
        self.stop_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                      help='Names of VMs')

        # Add arguments for resetting a VM
        self.reset_parser = self.subparsers.add_parser('reset', help='Reset VM',
                                                       parents=[self.parent_parser])
        self.reset_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                       help='Names of VM')

        # Add arguments for shutting down a VM
        self.shutdown_parser = self.subparsers.add_parser('shutdown', help='Shutdown VM',
                                                          parents=[self.parent_parser])
        self.shutdown_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                          help='Names of VMs')

        # Add arguments for fixing deadlock on a vm
        self.method_lock_parser = self.subparsers.add_parser(
            'clear-method-lock',
            help='Resolve the lock of a call to a method on the MCVirt daemon.',
            parents=[self.parent_parser]
        )

        # Add arguments for ISO functions
        self.iso_parser = self.subparsers.add_parser('iso', help='ISO managment',
                                                     parents=[self.parent_parser])

        self.iso_subparser = self.iso_parser.add_subparsers(dest='iso_action',
                                                            help='ISO action to perform',
                                                            metavar='Action')

        self.delete_iso_subparser = self.iso_subparser.add_parser('delete', help='Delete an ISO',
                                                                  parents=[self.parent_parser])
        self.delete_iso_subparser.add_argument('delete_path', metavar='NAME', type=str,
                                               help='ISO to delete')

        self.list_iso_subparser = self.iso_subparser.add_parser('list', help='List available ISOs',
                                                                parents=[self.parent_parser])

        self.add_iso_subparser = self.iso_subparser.add_parser('add', help='Add an ISO',
                                                               parents=[self.parent_parser])
        self.add_iso_subparser.add_argument('iso_name', metavar='ISO', type=str,
                                            help='Path/URL of ISO to add')

        self.add_iso_methods = self.add_iso_subparser.add_mutually_exclusive_group(required=True)
        self.add_iso_methods.add_argument('--from-path', dest='add_path', action='store_true',
                                          help='Copy an ISO to ISO directory')
        self.add_iso_methods.add_argument('--from-url', dest='add_url', action='store_true',
                                          help='Download and add an ISO')

        for parser in [self.iso_parser, self.delete_iso_subparser, self.list_iso_subparser,
                       self.add_iso_subparser]:
            parser.add_argument('--node', dest='iso_node',
                                help='Specify the node to perform the action on',
                                metavar='Node', default=None)

        # Add arguments for managing users
        self.user_parser = self.subparsers.add_parser('user', help='User managment',
                                                      parents=[self.parent_parser])
        self.user_subparser = self.user_parser.add_subparsers(
            dest='user_action',
            help='User managment action to perform',
            metavar='Action'
        )
        self.change_password_subparser = self.user_subparser.add_parser(
            'change-password',
            help='Change a user password',
            parents=[self.parent_parser]
        )
        self.change_password_subparser.add_argument(
            '--new-password',
            dest='new_password',
            metavar='New password',
            help='The new password'
        )
        self.change_password_subparser.add_argument(
            '--target-user',
            dest='target_user',
            metavar='Target user',
            help='The user to change the password of'
        )
        self.create_user_subparser = self.user_subparser.add_parser(
            'create',
            help='Create a new user',
            parents=[self.parent_parser]
        )
        self.create_user_subparser.add_argument(
            'new_username',
            metavar='User',
            type=str,
            help='The new user to create'
        )
        self.create_user_mut_ex_group = self.create_user_subparser.add_mutually_exclusive_group(
            required=False
        )
        self.create_user_mut_ex_group.add_argument(
            '--user-password',
            dest='new_user_password',
            metavar='New password',
            help='The password for the new user'
        )
        self.create_user_mut_ex_group.add_argument(
            '--generate-password',
            dest='generate_password',
            action='store_true',
            help='Generate a password for the new user'
        )
        self.delete_user_subparser = self.user_subparser.add_parser(
            'delete',
            help='Delete a user',
            parents=[self.parent_parser]
        )
        self.delete_user_subparser.add_argument(
            'delete_username',
            metavar='User',
            type=str,
            help='The user to delete'
        )

        # Add arguments for creating a VM
        self.create_parser = self.subparsers.add_parser('create', help='Create VM',
                                                        parents=[self.parent_parser])
        self.create_parser.add_argument('--memory', dest='memory', metavar='Memory',
                                        required=True, type=int,
                                        help='Amount of memory to allocate to the VM (MiB)')
        self.create_parser.add_argument('--disk-size', dest='disk_size', metavar='Disk Size',
                                        type=int, default=None,
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
                                             ' hosted on, if a Drbd storage-type' +
                                             ' is specified',
                                        default=[])

        self.create_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        # Determine if machine is configured to use Drbd
        self.create_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type',
                                        type=str, default=None, choices=['Local', 'Drbd'])
        self.create_parser.add_argument('--hdd-driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)
        self.create_parser.add_argument('--graphics-driver', dest='graphics_driver',
                                        metavar='Graphics Driver', type=str,
                                        help='Driver for graphics', default=None)
        self.create_parser.add_argument('--modification-flag', help='Add VM modification flag',
                                        dest='modification_flags', action='append')

        # Get arguments for deleting a VM
        self.delete_parser = self.subparsers.add_parser('delete', help='Delete VM',
                                                        parents=[self.parent_parser])
        self.delete_parser.add_argument('--delete-data', dest='delete_data', action='store_true',
                                        help='Deletes the VM data from the host')
        self.delete_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Get arguments for registering a VM
        self.register_parser = self.subparsers.add_parser('register', help='Registers a VM on' +
                                                                           ' the local node',
                                                          parents=[self.parent_parser])
        self.register_parser.add_argument('vm_name', metavar='VM Name', type=str,
                                          help='Name of VM')

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
        self.update_parser.add_argument('--delete-disk', dest='delete_disk', metavar='Disk ID',
                                        type=int, help='Remove a hard drive from a VM')
        self.update_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type', type=str,
                                        default=None, choices=['Local', 'Drbd'])
        self.update_parser.add_argument('--hdd-driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)
        self.update_parser.add_argument('--graphics-driver', metavar='Graphics Driver',
                                        dest='graphics_driver', type=str,
                                        help='Driver for graphics',
                                        default=None)
        self.update_parser.add_argument('--increase-disk', dest='increase_disk',
                                        metavar='Increase Disk', type=int,
                                        help='Increases VM disk by provided amount (MB)')
        self.update_parser.add_argument('--disk-id', dest='disk_id', metavar='Disk Id', type=int,
                                        help='The ID of the disk to be increased by')
        self.update_parser.add_argument('--attach-iso', '--iso', dest='iso', metavar='ISO Name',
                                        type=str, default=None, nargs='?',
                                        help=('Attach an ISO to a running VM.'
                                              ' Specify without value to detach ISO.'))
        self.update_parser.add_argument('--attach-usb-device', dest='attach_usb_device',
                                        metavar='bus,device', help=('Specify bus/device for USB '
                                                                    'device to connect, e.g. 5,2'),
                                        type=str, default=None)
        self.update_parser.add_argument('--detach-usb-device', dest='detach_usb_device',
                                        metavar='bus,device', help=('Specify bus/device for USB '
                                                                    'device to detach, e.g. 5,2'),
                                        type=str, default=None)
        self.vm_autostart_mutual_group = self.update_parser.add_mutually_exclusive_group(
            required=False
        )
        self.vm_autostart_mutual_group.add_argument('--autostart-on-boot', action='store_true',
                                                    dest='autostart_boot',
                                                    help=('Update VM to automatically '
                                                          'start on boot'))
        self.vm_autostart_mutual_group.add_argument('--autostart-on-poll', action='store_true',
                                                    dest='autostart_poll',
                                                    help=('Update VM to automatically start on '
                                                          'autostart watchdog poll'))
        self.vm_autostart_mutual_group.add_argument('--autostart-disable', action='store_true',
                                                    dest='autostart_disable',
                                                    help='Disable autostart of VM')
        self.update_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        self.update_parser.add_argument('--add-flag', help='Add VM modification flag',
                                        dest='add_flags', action='append')
        self.update_parser.add_argument('--remove-flag', help='Remove VM modification flag',
                                        dest='remove_flags', action='append')

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
        self.list_parser.add_argument('--cpu', dest='include_cpu', help='Include CPU column',
                                      action='store_true')
        self.list_parser.add_argument('--memory', '--ram', dest='include_ram',
                                      help='Include RAM column', action='store_true')
        self.list_parser.add_argument('--disk-size', '--hdd', dest='include_disk',
                                      help='Include HDD column', action='store_true')

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
        self.move_parser = self.subparsers.add_parser('move', help=('Move a VM and related storage'
                                                                    ' to another node'),
                                                      parents=[self.parent_parser])
        self.move_parser.add_argument('--source-node', dest='source_node',
                                      help="The node that the VM will be moved from.\n" +
                                      'For Drbd VMs, the source node must not be' +
                                      " the local node.\nFor Local VMs, the node" +
                                      " must be the local node, but may be omitted.")
        self.move_parser.add_argument('--destination-node', dest='destination_node',
                                      help='The node that the VM will be moved to')
        self.move_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create sub-parser for cluster-related commands
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
        self.node_cluster_config = self.node_parser.add_argument_group(
            'Storage', 'Configure the node-specific storage configurations'
        )
        self.node_cluster_config.add_argument('--set-vm-vg', dest='volume_group',
                                              metavar='VM Volume Group',
                                              help=('Sets the local volume group used for Virtual'
                                                    ' machine HDD logical volumes'))

        self.node_watchdog_parser = self.node_parser.add_argument_group(
            'Watchdog', 'Update configurations for watchdogs'
        )
        self.node_watchdog_parser.add_argument('--set-autostart-interval',
                                               dest='autostart_interval',
                                               metavar='Autostart Time (Seconds)',
                                               help=('Set the interval period (seconds) for '
                                                     'the autostart watchdog. '
                                                     'Setting to \'0\' will disable the '
                                                     'watchdog polling.'),
                                               type=int)
        self.node_watchdog_parser.add_argument('--get-autostart-interval',
                                               dest='get_autostart_interval',
                                               action='store_true',
                                               help='Return the current autostart interval.')

        self.node_cluster_config = self.node_parser.add_argument_group(
            'Cluster', 'Configure the node-specific cluster configurations'
        )
        self.node_cluster_config.add_argument('--set-ip-address', dest='ip_address',
                                              metavar='Cluster IP Address',
                                              help=('Sets the cluster IP address'
                                                    ' for the local node,'
                                                    ' used for Drbd and cluster management.'))

        self.ldap_parser = self.node_parser.add_argument_group(
            'Ldap', 'Configure the LDAP authentication backend'
        )
        self.ldap_enable_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_enable_mutual_group.add_argument('--enable-ldap', dest='ldap_enable',
                                                   action='store_true', default=None,
                                                   help='Enable the LDAP authentication backend')
        self.ldap_enable_mutual_group.add_argument('--disable-ldap', dest='ldap_disable',
                                                   action='store_true',
                                                   help='Disable the LDAP authentication backend')

        self.ldap_server_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_server_mutual_group.add_argument('--server-uri', dest='ldap_server_uri',
                                                   metavar='LDAP Server URI', default=None,
                                                   help=('Specify the LDAP server URI.'
                                                         ' E.g. ldap://10.200.1.1:389'
                                                         ' ldaps://10.200.1.1'))
        self.ldap_server_mutual_group.add_argument('--clear-server-uri',
                                                   action='store_true',
                                                   dest='ldap_server_uri_clear',
                                                   help='Clear the server URI configuration.')
        self.ldap_base_dn_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_base_dn_mutual_group.add_argument('--base-dn', dest='ldap_base_dn',
                                                    metavar='LDAP Base DN', default=None,
                                                    help=('Base search DN for users. E.g. '
                                                          'ou=People,dc=my,dc=company,dc=com'))
        self.ldap_base_dn_mutual_group.add_argument('--clear-base-dn',
                                                    action='store_true',
                                                    dest='ldap_base_dn_clear',
                                                    help='Clear the base DN configuration.')
        self.ldap_bind_dn_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_bind_dn_mutual_group.add_argument('--bind-dn', dest='ldap_bind_dn',
                                                    metavar='LDAP Bind DN', default=None,
                                                    help=('DN for user to bind to LDAP. E.g. '
                                                          'cn=Admin,ou=People,dc=my,dc=company,'
                                                          'dc=com'))
        self.ldap_bind_dn_mutual_group.add_argument('--clear-bind-dn',
                                                    action='store_true',
                                                    dest='ldap_bind_dn_clear',
                                                    help='Clear the bind DN configuration.')
        self.ldap_base_pw_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_base_pw_mutual_group.add_argument('--bind-pass', dest='ldap_bind_pass',
                                                    metavar='LDAP Bind Password', default=None,
                                                    help='Password for bind account')
        self.ldap_base_pw_mutual_group.add_argument('--clear-bind-pass',
                                                    action='store_true',
                                                    dest='ldap_bind_pass_clear',
                                                    help='Clear the bind pass configuration.')
        self.ldap_user_search_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_user_search_mutual_group.add_argument('--user-search', dest='ldap_user_search',
                                                        metavar='LDAP search', default=None,
                                                        help=('LDAP query for user objects. E.g.'
                                                              ' (objectClass=posixUser)'))
        self.ldap_user_search_mutual_group.add_argument('--clear-user-search',
                                                        action='store_true',
                                                        dest='ldap_user_search_clear',
                                                        help='Clear the user search configuration')
        self.ldap_username_attribute_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_username_attribute_mutual_group.add_argument('--username-attribute',
                                                               default=None,
                                                               dest='ldap_username_attribute',
                                                               metavar='LDAP Username Attribute',
                                                               help=('LDAP username attribute.'
                                                                     ' E.g. uid'))
        self.ldap_username_attribute_mutual_group.add_argument(
            '--clear-username-attribute',
            action='store_true',
            dest='ldap_username_attribute_clear',
            help='Clear the username attribute configuration'
        )
        self.ldap_ca_cert_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_ca_cert_mutual_group.add_argument('--ca-cert-file', dest='ldap_ca_cert',
                                                    metavar='Path to CA file', default=None,
                                                    help=('Path to CA cert file for LDAP over'
                                                          ' TLS.'))
        self.ldap_ca_cert_mutual_group.add_argument('--clear-ca-cert-file',
                                                    action='store_true',
                                                    dest='ldap_ca_cert_clear',
                                                    help='Clear the store LDAP CA cert file.')

        # Create sub-parser for VM verification
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

        # Create sub-parser for VM verification
        self.verify_parser = self.subparsers.add_parser(
            'resync',
            help='Perform resync of DRBD volumes',
            parents=[self.parent_parser])
        self.resync_node_mutual_exclusive_group = self.verify_parser.add_mutually_exclusive_group(
            required=True
        )
        self.resync_node_mutual_exclusive_group.add_argument(
            '--source-node', dest='resync_node', default=None,
            help='Specify the SOURCE node for the resync.'
        )
        self.resync_node_mutual_exclusive_group.add_argument(
            '--auto-determine', dest='resync_auto_determine', action='store_true',
            help='Automatically sync from the node that the VM is currently registered on.'
        )
        self.verify_parser.add_argument('vm_name', metavar='VM Name',
                                        help='Specify a single VM to resync')
        self.verify_parser.add_argument('--disk-id', metavar='Disk Id', default=1, type=int,
                                        help='Specify the Disk ID to resync (default: 1)')

        # Create sub-parser for Drbd-related commands
        self.drbd_parser = self.subparsers.add_parser('drbd', help='Manage Drbd clustering',
                                                      parents=[self.parent_parser])
        self.drbd_subparser = self.drbd_parser.add_subparsers(dest='drbd_action', metavar='Action',
                                                              help='Drbd action to perform')
        self.drbd_subparser.add_parser('enable', help='Enable Drbd support on the cluster',
                                       parents=[self.parent_parser])
        self.drbd_subparser.add_parser('list', help='List Drbd volumes on the system',
                                       parents=[self.parent_parser])

        # Create sub-parser for backup commands
        self.backup_parser = self.subparsers.add_parser('backup',
                                                        help='Performs backup-related tasks',
                                                        parents=[self.parent_parser])
        self.backup_subparser = self.backup_parser.add_subparsers(
            dest='backup_action',
            metavar='Action',
            help='Backup action to perform'
        )
        self.create_snapshot_subparser = self.backup_subparser.add_parser(
            'create-snapshot',
            help='Create a snapshot of the specified disk',
            parents=[self.parent_parser]
        )
        self.delete_snapshot_subparser = self.backup_subparser.add_parser(
            'delete-snapshot',
            help='Delete the snapshot of the specified disk',
            parents=[self.parent_parser]
        )
        for parser in [self.create_snapshot_subparser, self.delete_snapshot_subparser]:
            parser.add_argument(
                '--disk-id',
                dest='disk_id',
                metavar='Disk Id',
                type=int,
                required=True,
                help='The ID of the disk to manage the backup snapshot of'
            )
            parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

        # Create sub-parser for managing VM locks
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

    def print_status(self, status):
        """Print if the user has specified that the parser should print statuses."""
        if self.verbose:
            print status

    def parse_arguments(self, script_args=None):
        """Parse arguments and performs actions based on the arguments."""
        # If arguments have been specified, split, so that
        # an array is sent to the argument parser
        if (script_args is not None):
            script_args = script_args.split()

        args = self.parser.parse_args(script_args)
        action = args.action

        ignore_cluster = False

        if args.ignore_failed_nodes:
            # If the user has specified to ignore the cluster,
            # print a warning and confirm the user's answer
            if not args.accept_failed_nodes_warning:
                self.print_status(('WARNING: Running MCVirt with --ignore-failed-nodes'
                                   ' can leave the cluster in an inconsistent state!'))
                continue_answer = System.getUserInput('Would you like to continue? (Y/n): ')

                if continue_answer.strip() is not 'Y':
                    self.print_status('Cancelled...')
                    return
            ignore_cluster = True

        rpc = None
        auth_cache_file = os.getenv('HOME') + '/' + self.AUTH_FILE
        if self.SESSION_ID and self.USERNAME:
            rpc = Connection(username=self.USERNAME, session_id=self.SESSION_ID,
                             ignore_cluster=ignore_cluster)
        else:
            # Obtain connection to Pyro server
            use_auth_session = False
            if not (args.password or args.username):
                # Try logging in with saved session
                auth_session = None
                try:
                    with open(auth_cache_file, 'r') as f:
                        auth_username = f.readline().strip()
                        auth_session = f.readline().strip()
                except IOError:
                    pass

                if auth_session:
                    try:
                        rpc = Connection(username=auth_username, session_id=auth_session,
                                         ignore_cluster=ignore_cluster)
                        self.SESSION_ID = rpc.session_id
                        self.USERNAME = rpc.username
                    except AuthenticationError:
                        self.print_status('Authentication error occured when using saved session.')
                        try:
                            os.remove(auth_cache_file)
                        except:
                            pass
                        rpc = None

            if not rpc:
                # Check if user/password have been passed. Else, ask for them.
                username = args.username if args.username else System.getUserInput(
                    'Username: '
                ).rstrip()
                if args.password:
                    password = args.password
                else:
                    password = System.getUserInput(
                        'Password: ', password=True
                    ).rstrip()
                rpc = Connection(username=username, password=password,
                                 ignore_cluster=ignore_cluster)
                self.SESSION_ID = rpc.session_id
                self.USERNAME = rpc.username

        # If successfully authenticated then store session ID and username in auth file
        if args.cache_credentials:
            try:
                with open(auth_cache_file, 'w') as f:
                    f.write("%s\n%s" % (rpc.username, rpc.session_id))
            except:
                pass

        if args.ignore_drbd:
            rpc.ignore_drbd()

        # Perform functions on the VM based on the action passed to the script
        if action == 'start':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            for vm_name in args.vm_names:
                try:
                    vm_object = vm_factory.getVirtualMachineByName(vm_name)
                    rpc.annotate_object(vm_object)
                    vm_object.start(iso_name=args.iso)
                    self.print_status('Successfully started VM %s' % vm_name)
                except Exception:
                    self.print_status('Error while starting VM %s' % vm_name)
                    raise

        elif action == 'stop':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            for vm_name in args.vm_names:
                try:
                    vm_object = vm_factory.getVirtualMachineByName(vm_name)
                    rpc.annotate_object(vm_object)
                    vm_object.stop()
                    self.print_status('Successfully stopped VM %s' % vm_name)
                except Exception:
                    self.print_status('Error while stopping VM %s:' % vm_name)
                    raise

        elif action == 'reset':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            for vm_name in args.vm_names:
                try:
                    vm_object = vm_factory.getVirtualMachineByName(vm_name)
                    rpc.annotate_object(vm_object)
                    vm_object.reset()
                    self.print_status('Successfully reset VM %s' % vm_name)
                except Exception:
                    self.print_status('Error while resetting VM %s' % vm_name)
                    raise

        elif action == 'shutdown':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            for vm_name in args.vm_names:
                try:
                    vm_object = vm_factory.getVirtualMachineByName(vm_name)
                    rpc.annotate_object(vm_object)
                    vm_object.shutdown()
                    self.print_status('Successfully shutting down VM %s' % vm_name)
                except Exception:
                    self.print_status('Error while initiating shutdown of VM %s:' % vm_name)
                    raise

        elif action == 'clear-method-lock':
            node = rpc.get_connection('node')
            if node.clear_method_lock():
                self.print_status('Successfully cleared method lock')
            else:
                self.print_status('method lock already cleared')

        elif action == 'create':
            storage_type = args.storage_type or None

            # Convert memory allocation from MiB to KiB
            memory_allocation = int(args.memory) * 1024
            vm_factory = rpc.get_connection('virtual_machine_factory')
            hard_disks = [args.disk_size] if args.disk_size is not None else []
            mod_flags = args.modification_flags or []
            vm_object = vm_factory.create(
                name=args.vm_name,
                cpu_cores=args.cpu_count,
                memory_allocation=memory_allocation,
                hard_drives=hard_disks,
                network_interfaces=args.networks,
                storage_type=storage_type,
                hard_drive_driver=args.hard_disk_driver,
                graphics_driver=args.graphics_driver,
                available_nodes=args.nodes,
                modification_flags=mod_flags)

        elif action == 'delete':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            vm_object.delete(args.delete_data)

        elif action == 'register':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            vm_object.register()

        elif action == 'unregister':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            vm_object.unregister()

        elif action == 'update':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)

            if args.memory:
                old_ram_allocation_kib = vm_object.getRAM()
                old_ram_allocation = int(old_ram_allocation_kib) / 1024
                new_ram_allocation = int(args.memory) * 1024
                vm_object.updateRAM(new_ram_allocation, old_value=old_ram_allocation_kib)
                self.print_status(
                    'RAM allocation will be changed from %sMiB to %sMiB.' %
                    (old_ram_allocation, args.memory)
                )

            if args.cpu_count:
                old_cpu_count = vm_object.getCPU()
                vm_object.updateCPU(args.cpu_count, old_value=old_cpu_count)
                self.print_status(
                    'Number of virtual cores will be changed from %s to %s.' %
                    (old_cpu_count, args.cpu_count)
                )

            if args.remove_network:
                network_adapter_factory = rpc.get_connection('network_adapter_factory')
                network_adapter_object = network_adapter_factory.getNetworkAdapterByMacAdress(
                    vm_object, args.remove_network
                )
                rpc.annotate_object(network_adapter_object)
                network_adapter_object.delete()

            if args.add_network:
                network_factory = rpc.get_connection('network_factory')
                network_adapter_factory = rpc.get_connection('network_adapter_factory')
                network_object = network_factory.get_network_by_name(args.add_network)
                rpc.annotate_object(network_object)
                network_adapter_factory.create(vm_object, network_object)

            if args.add_disk:
                hard_drive_factory = rpc.get_connection('hard_drive_factory')
                hard_drive_factory.create(vm_object, size=args.add_disk,
                                          storage_type=args.storage_type,
                                          driver=args.hard_disk_driver)
            if args.delete_disk:
                hard_drive_factory = rpc.get_connection('hard_drive_factory')
                hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
                rpc.annotate_object(hard_drive_object)
                hard_drive_object.increaseSize(args.delete())

            if args.increase_disk and args.disk_id:
                hard_drive_factory = rpc.get_connection('hard_drive_factory')
                hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
                rpc.annotate_object(hard_drive_object)
                hard_drive_object.increaseSize(args.increase_disk)

            if args.iso or args.iso is None:
                vm_object.update_iso(args.iso)

            if args.graphics_driver:
                vm_object.update_graphics_driver(args.graphics_driver)

            if args.autostart_boot:
                vm_object.set_autostart_state('ON_BOOT')
            elif args.autostart_poll:
                vm_object.set_autostart_state('ON_POLL')
            else:
                vm_object.set_autostart_state('NO_AUTOSTART')

            if args.attach_usb_device:
                usb_device = vm_object.get_usb_device(*args.attach_usb_device.split(','))
                rpc.annotate_object(usb_device)
                usb_device.attach()
            if args.detach_usb_device:
                usb_device = vm_object.get_usb_device(*args.detach_usb_device.split(','))
                rpc.annotate_object(usb_device)
                usb_device.detach()

            if args.add_flags or args.remove_flags:
                add_flags = args.add_flags or []
                remove_flags = args.remove_flags or []
                vm_object.update_modification_flags(add_flags=add_flags, remove_flags=remove_flags)
                flags_str = ", ".join(vm_object.get_modification_flags())
                self.print_status('Modification flags set to: %s' % (flags_str or 'None'))

        elif action == 'permission':
            if (args.add_superuser or args.delete_superuser) and args.vm_name:
                raise ArgumentParserException('Superuser groups are global-only roles')

            if args.vm_name:
                vm_factory = rpc.get_connection('virtual_machine_factory')
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                rpc.annotate_object(vm_object)
                permission_destination_string = 'role on VM %s' % vm_object.get_name()
            else:
                vm_object = None
                permission_destination_string = 'global role'

            auth_object = rpc.get_connection('auth')
            rpc.annotate_object(auth_object)
            user_factory = rpc.get_connection('user_factory')
            rpc.annotate_object(user_factory)

            if args.add_user:
                user_object = user_factory.get_user_by_username(args.add_user)
                rpc.annotate_object(user_object)
                auth_object.add_user_permission_group(
                    permission_group='user',
                    user_object=user_object,
                    vm_object=vm_object)
                self.print_status(
                    'Successfully added \'%s\' to \'user\' %s' %
                    (args.add_user, permission_destination_string))

            if args.delete_user:
                user_object = user_factory.get_user_by_username(args.delete_user)
                rpc.annotate_object(user_object)
                auth_object.delete_user_permission_group(
                    permission_group='user',
                    user_object=user_object,
                    vm_object=vm_object)
                self.print_status(
                    'Successfully removed \'%s\' from \'user\' %s' %
                    (args.delete_user, permission_destination_string))

            if args.add_owner:
                user_object = user_factory.get_user_by_username(args.add_owner)
                rpc.annotate_object(user_object)
                auth_object.add_user_permission_group(
                    permission_group='owner',
                    user_object=user_object,
                    vm_object=vm_object)
                self.print_status(
                    'Successfully added \'%s\' to \'owner\' %s' %
                    (args.add_owner, permission_destination_string))

            if args.delete_owner:
                user_object = user_factory.get_user_by_username(args.delete_owner)
                rpc.annotate_object(user_object)
                auth_object.delete_user_permission_group(
                    permission_group='owner',
                    user_object=user_object,
                    vm_object=vm_object)
                self.print_status(
                    'Successfully removed \'%s\' from \'owner\' %s' %
                    (args.delete_owner, permission_destination_string))

            if args.add_superuser:
                user_object = user_factory.get_user_by_username(args.add_superuser)
                rpc.annotate_object(user_object)
                auth_object.add_superuser(user_object=user_object)
                self.print_status('Successfully added %s to the global superuser group' %
                                  args.add_superuser)
            if args.delete_superuser:
                user_object = user_factory.get_user_by_username(args.delete_superuser)
                rpc.annotate_object(user_object)
                auth_object.delete_superuser(user_object=user_object)
                self.print_status('Successfully removed %s from the global superuser group ' %
                                  args.delete_superuser)

        elif action == 'info':
            if not args.vm_name and (args.vnc_port or args.node):
                self.parser.error('Must provide a VM Name')
            if args.vm_name:
                vm_factory = rpc.get_connection('virtual_machine_factory')
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                rpc.annotate_object(vm_object)
                if args.vnc_port:
                    self.print_status(vm_object.getVncPort())
                elif args.node:
                    self.print_status(vm_object.getNode())
                else:
                    self.print_status(vm_object.getInfo())
            else:
                cluster_object = rpc.get_connection('cluster')
                self.print_status(cluster_object.print_info())

        elif action == 'network':
            network_factory = rpc.get_connection('network_factory')
            if args.network_action == 'create':
                network_factory.create(args.network, physical_interface=args.interface)
            elif args.network_action == 'delete':
                network_object = network_factory.get_network_by_name(args.network)
                rpc.annotate_object(network_object)
                network_object.delete()
            elif args.network_action == 'list':
                self.print_status(network_factory.get_network_list_table())

        elif action == 'migrate':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            if args.online_migration:
                vm_object.onlineMigrate(args.destination_node)
            else:
                vm_object.offlineMigrate(
                    args.destination_node,
                    wait_for_vm_shutdown=args.wait_for_shutdown,
                    start_after_migration=args.start_after_migration
                )
            self.print_status('Successfully migrated \'%s\' to %s' %
                              (vm_object.get_name(), args.destination_node))

        elif action == 'move':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            vm_object.move(destination_node=args.destination_node,
                           source_node=args.source_node)

        elif action == 'cluster':
            cluster_object = rpc.get_connection('cluster')
            if args.cluster_action == 'get-connect-string':
                self.print_status(cluster_object.get_connection_string())
            if args.cluster_action == 'add-node':
                if args.connect_string:
                    connect_string = args.connect_string
                else:
                    connect_string = System.getUserInput('Enter Connect String: ')
                cluster_object.add_node(connect_string)
                self.print_status('Successfully added node')
            if args.cluster_action == 'remove-node':
                cluster_object.remove_node(args.node)
                self.print_status('Successfully removed node %s' % args.node)

        elif action == 'node':
            node = rpc.get_connection('node')
            ldap = rpc.get_connection('ldap_factory')
            if args.volume_group:
                node.set_storage_volume_group(args.volume_group)
                self.print_status('Successfully set VM storage volume group to %s' %
                                  args.volume_group)

            if args.ip_address:
                node.set_cluster_ip_address(args.ip_address)
                self.print_status('Successfully set cluster IP address to %s' % args.ip_address)

            if args.autostart_interval or args.autostart_interval == 0:
                autostart_watchdog = rpc.get_connection('autostart_watchdog')
                autostart_watchdog.set_autostart_interval(args.autostart_interval)
            elif args.get_autostart_interval:
                autostart_watchdog = rpc.get_connection('autostart_watchdog')
                self.print_status(autostart_watchdog.get_autostart_interval())

            if args.ldap_enable:
                ldap.set_enable(True)
            elif args.ldap_disable:
                ldap.set_enable(False)

            ldap_args = {}
            if args.ldap_server_uri is not None:
                ldap_args['server_uri'] = args.ldap_server_uri
            elif args.ldap_server_uri_clear:
                ldap_args['server_uri'] = None
            if args.ldap_base_dn is not None:
                ldap_args['base_dn'] = args.ldap_base_dn
            elif args.ldap_base_dn_clear:
                ldap_args['base_dn'] = None
            if args.ldap_bind_dn is not None:
                ldap_args['bind_dn'] = args.ldap_bind_dn
            elif args.ldap_bind_dn_clear:
                ldap_args['bind_dn'] = None
            if args.ldap_bind_pass is not None:
                ldap_args['bind_pass'] = args.ldap_bind_pass
            elif args.ldap_bind_pass_clear:
                ldap_args['bind_pass'] = None
            if args.ldap_user_search is not None:
                ldap_args['user_search'] = args.ldap_user_search
            elif args.ldap_user_search_clear:
                ldap_args['user_search'] = None
            if args.ldap_username_attribute is not None:
                ldap_args['username_attribute'] = args.ldap_username_attribute
            elif args.ldap_username_attribute_clear:
                ldap_args['username_attribute'] = None
            if args.ldap_ca_cert:
                if not os.path.exists(args.ldap_ca_cert):
                    raise Exception('Specified LDAP CA cert file cannot be found.')
                with open(args.ldap_ca_cert, 'r') as ca_crt_fh:
                    ldap_args['ca_cert'] = ca_crt_fh.read()
            elif args.ldap_ca_cert_clear:
                ldap_args['ca_cert'] = None

            if len(ldap_args):
                ldap.set_config(**ldap_args)

        elif action == 'verify':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            if args.vm_name:
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                rpc.annotate_object(vm_object)
                vm_objects = [vm_object]
            elif args.all:
                vm_objects = vm_factory.getAllVirtualMachines()

            # Iterate over the VMs and check each disk
            failures = []
            for vm_object in vm_objects:
                rpc.annotate_object(vm_object)
                for disk_object in vm_object.getHardDriveObjects():
                    rpc.annotate_object(disk_object)
                    if disk_object.get_type() == 'Drbd':
                        # Catch any exceptions due to the Drbd volume not being in-sync
                        try:
                            disk_object.verify()
                            self.print_status(
                                ('Drbd verification for %s completed '
                                 'without out-of-sync blocks') %
                                vm_object.get_name()
                            )
                        except DrbdVolumeNotInSyncException, e:
                            # Append the not-in-sync exception message to an array,
                            # so the rest of the disks can continue to be checked
                            failures.append(e.message)

            # If there were any failures during the verification, raise the exception and print
            # all exception messages
            if failures:
                raise DrbdVolumeNotInSyncException("\n".join(failures))

        elif action == 'resync':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            hard_drive_factory = rpc.get_connection('hard_drive_factory')
            disk_object = hard_drive_factory.getObject(vm_object, args.disk_id)
            rpc.annotate_object(disk_object)
            disk_object.resync(source_node=args.resync_node,
                               auto_determine=args.resync_auto_determine)

        elif action == 'drbd':
            node_drbd = rpc.get_connection('node_drbd')
            if args.drbd_action == 'enable':
                node_drbd.enable()
            if args.drbd_action == 'list':
                self.print_status(node_drbd.list())

        elif action == 'backup':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            hard_drive_factory = rpc.get_connection('hard_drive_factory')
            hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
            rpc.annotate_object(hard_drive_object)
            if args.backup_action == 'create-snapshot':
                self.print_status(hard_drive_object.createBackupSnapshot())
            elif args.backup_action == 'delete-snapshot':
                hard_drive_object.deleteBackupSnapshot()

        elif action == 'lock':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            rpc.annotate_object(vm_object)
            if args.lock:
                vm_object.setLockState(LockStates.LOCKED.value)
            if args.unlock:
                vm_object.setLockState(LockStates.UNLOCKED.value)
            if args.check_lock:
                self.print_status(LockStates(vm_object.getLockState()).name)

        elif action == 'clone':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.template)
            rpc.annotate_object(vm_object)
            vm_object.clone(args.vm_name)

        elif action == 'duplicate':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.template)
            rpc.annotate_object(vm_object)
            vm_object.duplicate(args.vm_name)

        elif action == 'list':
            vm_factory = rpc.get_connection('virtual_machine_factory')
            self.print_status(vm_factory.listVms(include_cpu=args.include_cpu,
                                                 include_ram=args.include_ram,
                                                 include_disk=args.include_disk))

        elif action == 'iso':
            iso_factory = rpc.get_connection('iso_factory')
            if args.iso_action == 'list':
                self.print_status(iso_factory.get_iso_list(node=args.iso_node))

            if args.iso_action == 'add' and args.add_path:
                if args.iso_node:
                    raise ArgumentParserException('Cannot add to remote node from local path')
                iso_writer = iso_factory.add_iso_from_stream(args.iso_name)
                rpc.annotate_object(iso_writer)
                with open(args.iso_name, 'rb') as iso_fh:
                    while True:
                        data_chunk = iso_fh.read(1024)
                        if data_chunk:
                            data_chunk = binascii.hexlify(data_chunk)
                            iso_writer.write_data(data_chunk)
                        else:
                            break
                iso_object = iso_writer.write_end()
                rpc.annotate_object(iso_object)
                self.print_status('Successfully added ISO: %s' % iso_object.get_name())

            if args.iso_action == 'add' and args.add_url:
                iso_name = iso_factory.add_from_url(args.iso_name, node=args.iso_node)
                self.print_status('Successfully added ISO: %s' % iso_name)

            if args.iso_action == 'delete':
                if args.iso_node:
                    raise ArgumentParserException('Cannot remove ISO from remote node')
                iso_object = iso_factory.get_iso_by_name(args.delete_path)
                rpc.annotate_object(iso_object)
                iso_object.delete()
                self.print_status('Successfully removed iso: %s' % args.delete_path)

        elif action == 'user':
            if args.user_action == 'change-password':
                user_factory = rpc.get_connection('user_factory')
                target_user = args.target_user or self.USERNAME
                user = user_factory.get_user_by_username(target_user)
                rpc.annotate_object(user)
                new_password = args.new_password or System.getNewPassword()
                user.set_password(new_password)

            elif args.user_action == 'create':
                user_factory = rpc.get_connection('user_factory')

                if args.generate_password:
                    new_password = UserBase.generate_password(10)
                else:
                    new_password = args.new_user_password or System.getNewPassword()

                user_factory.create(args.new_username, new_password)

                self.print_status('New user details:\nUsername: %s' % args.new_username)
                if args.generate_password:
                    self.print_status('Password: %s' % new_password)

            elif args.user_action == 'delete':
                user_factory = rpc.get_connection('user_factory')
                user = user_factory.get_user_by_username(args.delete_username)
                rpc.annotate_object(user)
                user.delete()

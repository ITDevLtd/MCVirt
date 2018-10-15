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
import os

from mcvirt.exceptions import (ArgumentParserException, DrbdVolumeNotInSyncException,
                               AuthenticationError)
from mcvirt.client.rpc import Connection
from mcvirt.system import System
from mcvirt.constants import LockStates
from mcvirt.parser_modules.virtual_machine.start_parser import StartParser
from mcvirt.parser_modules.virtual_machine.stop_parser import StopParser
from mcvirt.parser_modules.virtual_machine.reset_parser import ResetParser
from mcvirt.parser_modules.virtual_machine.shutdown_parser import ShutdownParser
from mcvirt.parser_modules.virtual_machine.create_parser import CreateParser
from mcvirt.parser_modules.virtual_machine.delete_parser import DeleteParser
from mcvirt.parser_modules.clear_method_lock_parser import ClearMethodLockParser
from mcvirt.parser_modules.iso_parser import IsoParser
from mcvirt.parser_modules.virtual_machine.register_parser import RegisterParser
from mcvirt.parser_modules.virtual_machine.unregister_parser import UnregisterParser
from mcvirt.parser_modules.virtual_machine.update_parser import UpdateParser
from mcvirt.parser_modules.virtual_machine.migrate_parser import MigrateParser
from mcvirt.parser_modules.virtual_machine.info_parser import InfoParser
from mcvirt.parser_modules.permission_parser import PermissionParser
from mcvirt.parser_modules.network_parser import NetworkParser
from mcvirt.parser_modules.group_parser import GroupParser
from mcvirt.parser_modules.user_parser import UserParser
from mcvirt.parser_modules.virtual_machine.list_parser import ListParser
from mcvirt.parser_modules.virtual_machine.duplicate_parser import DuplicateParser
from mcvirt.parser_modules.virtual_machine.clone_parser import CloneParser
from mcvirt.parser_modules.virtual_machine.move_parser import MoveParser
from mcvirt.parser_modules.cluster_parser import ClusterParser
from mcvirt.parser_modules.storage_parser import StorageParser


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

        self.global_option = self.parent_parser.add_argument_group('Global optional arguments')
        self.global_option.add_argument('--username', '-U', dest='username',
                                        help='MCVirt username')
        self.global_option.add_argument('--password', dest='password',
                                        help='MCVirt password')
        self.global_option.add_argument('--cache-credentials', dest='cache_credentials',
                                        action='store_true',
                                        help=('Store the session ID, so it can be used for '
                                              'multiple MCVirt calls.'))
        self.global_option.add_argument('--ignore-failed-nodes', dest='ignore_failed_nodes',
                                        help='Ignores nodes that are inaccessible',
                                        action='store_true')
        self.global_option.add_argument('--accept-failed-nodes-warning',
                                        dest='accept_failed_nodes_warning',
                                        help=argparse.SUPPRESS, action='store_true')
        self.global_option.add_argument('--ignore-drbd', dest='ignore_drbd',
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
        StartParser(self.subparsers, self.parent_parser)

        # Add arguments for stopping a VM
        StopParser(self.subparsers, self.parent_parser)

        # Add arguments for resetting a VM
        ResetParser(self.subparsers, self.parent_parser)

        # Add arguments for shutting down a VM
        ShutdownParser(self.subparsers, self.parent_parser)

        # Add arguments for fixing deadlock on a vm
        ClearMethodLockParser(self.subparsers, self.parent_parser)

        # Add arguments for ISO functions
        IsoParser(self.subparsers, self.parent_parser)

        # Add arguments for managing users
        UserParser(self.subparsers, self.parent_parser)

        # Add arguments for creating a VM
        CreateParser(self.subparsers, self.parent_parser)

        # Get arguments for deleting a VM
        DeleteParser(self.subparsers, self.parent_parser)

        RegisterParser(self.subparsers, self.parent_parser)
        UnregisterParser(self.subparsers, self.parent_parser)

        # Get arguments for updating a VM
        UpdateParser(self.subparsers, self.parent_parser)

        PermissionParser(self.subparsers, self.parent_parser)

        GroupParser(self.subparsers, self.parent_parser)

        # Create subparser for network-related commands
        NetworkParser(self.subparsers, self.parent_parser)

        # Get arguments for getting VM information
        InfoParser(self.subparsers, self.parent_parser)

        # Get arguments for listing VMs
        ListParser(self.subparsers, self.parent_parser)

        # Get arguments for cloning a VM
        CloneParser(self.subparsers, self.parent_parser)

        # Get arguments for cloning a VM
        DuplicateParser(self.subparsers, self.parent_parser)

        # Get arguments for migrating a VM
        MigrateParser(self.subparsers, self.parent_parser)

        # Create sub-parser for moving VMs
        MoveParser(self.subparsers, self.parent_parser)

        # Create sub-parser for cluster-related commands
        ClusterParser(self.subparsers, self.parent_parser)

        StorageParser(self.subparsers, self.parent_parser)

        # Create subparser for commands relating to the local node configuration
        self.node_parser = self.subparsers.add_parser(
            'node',
            help='Modify configurations relating to the local node',
            parents=[self.parent_parser]
        )

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

        self.rpc = None
        auth_cache_file = os.getenv('HOME') + '/' + self.AUTH_FILE
        if self.SESSION_ID and self.USERNAME:
            self.rpc = Connection(username=self.USERNAME, session_id=self.SESSION_ID,
                             ignore_cluster=ignore_cluster)
        else:
            # Obtain connection to Pyro server
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
                        self.rpc = Connection(username=auth_username, session_id=auth_session,
                                         ignore_cluster=ignore_cluster)
                        self.SESSION_ID = self.rpc.session_id
                        self.USERNAME = self.rpc.username
                    except AuthenticationError:
                        # If authentication fails with cached session,
                        # print error, attempt to remove sessionn file and
                        # remove rpc connection
                        self.print_status('Authentication error occured when using saved session.')
                        try:
                            os.remove(auth_cache_file)
                        except:
                            pass
                        self.rpc = None

            if not self.rpc:
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
                self.rpc = Connection(username=username, password=password,
                                 ignore_cluster=ignore_cluster)
                self.SESSION_ID = self.rpc.session_id
                self.USERNAME = self.rpc.username

        # If successfully authenticated then store session ID and username in auth file
        if args.cache_credentials:
            try:
                with open(auth_cache_file, 'w') as f:
                    f.write("%s\n%s" % (self.rpc.username, self.rpc.session_id))
            except:
                pass

        if args.ignore_drbd:
            self.rpc.ignore_drbd()

        # If a custom parser function has been defined, used this and exit
        # instead of running through (old) main parser workflow
        if 'func' in dir(args):
            args.func(args=args, p_=self)
            return

        elif action == 'node':
            node = self.rpc.get_connection('node')
            ldap = self.rpc.get_connection('ldap_factory')

            if args.ip_address:
                node.set_cluster_ip_address(args.ip_address)
                self.print_status('Successfully set cluster IP address to %s' % args.ip_address)

            if args.autostart_interval or args.autostart_interval == 0:
                autostart_watchdog = self.rpc.get_connection('autostart_watchdog')
                autostart_watchdog.set_autostart_interval(args.autostart_interval)
            elif args.get_autostart_interval:
                autostart_watchdog = self.rpc.get_connection('autostart_watchdog')
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
            vm_factory = self.rpc.get_connection('virtual_machine_factory')
            if args.vm_name:
                vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
                # TODO remove this line
                self.rpc.annotate_object(vm_object)
                vm_objects = [vm_object]
            elif args.all:
                vm_objects = vm_factory.getAllVirtualMachines()

            # Iterate over the VMs and check each disk
            failures = []
            for vm_object in vm_objects:
                self.rpc.annotate_object(vm_object)
                for disk_object in vm_object.getHardDriveObjects():
                    self.rpc.annotate_object(disk_object)
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
            vm_factory = self.rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            hard_drive_factory = self.rpc.get_connection('hard_drive_factory')
            disk_object = hard_drive_factory.getObject(vm_object, args.disk_id)
            self.rpc.annotate_object(disk_object)
            disk_object.resync(source_node=args.resync_node,
                               auto_determine=args.resync_auto_determine)

        elif action == 'drbd':
            node_drbd = self.rpc.get_connection('node_drbd')
            if args.drbd_action == 'enable':
                node_drbd.enable()
            if args.drbd_action == 'list':
                self.print_status(node_drbd.list())

        elif action == 'backup':
            vm_factory = self.rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            self.rpc.annotate_object(vm_object)
            hard_drive_factory = self.rpc.get_connection('hard_drive_factory')
            hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
            self.rpc.annotate_object(hard_drive_object)
            if args.backup_action == 'create-snapshot':
                self.print_status(hard_drive_object.createBackupSnapshot())
            elif args.backup_action == 'delete-snapshot':
                hard_drive_object.deleteBackupSnapshot()

        elif action == 'lock':
            vm_factory = self.rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            self.rpc.annotate_object(vm_object)
            if args.lock:
                vm_object.setLockState(LockStates.LOCKED.value)
            if args.unlock:
                vm_object.setLockState(LockStates.UNLOCKED.value)
            if args.check_lock:
                self.print_status(LockStates(vm_object.getLockState()).name)

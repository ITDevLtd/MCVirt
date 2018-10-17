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

from mcvirt.exceptions import (ArgumentParserException,
                               AuthenticationError)
from mcvirt.client.rpc import Connection
from mcvirt.system import System
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
from mcvirt.parser_modules.node_parser import NodeParser
from mcvirt.parser_modules.verify_parser import VerifyParser
from mcvirt.parser_modules.resync_parser import ResyncParser
from mcvirt.parser_modules.drbd_parser import DrbdParser
from mcvirt.parser_modules.virtual_machine.backup_parser import BackupParser
from mcvirt.parser_modules.virtual_machine.lock_parser import LockParser


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
        NodeParser(self.subparsers, self.parent_parser)

        # Create sub-parser for VM verification
        VerifyParser(self.subparsers, self.parent_parser)

        # Create sub-parser for VM Disk resync
        ResyncParser(self.subparsers, self.parent_parser)

        # Create sub-parser for Drbd-related commands
        DrbdParser(self.subparsers, self.parent_parser)

        # Create sub-parser for backup commands
        BackupParser(self.subparsers, self.parent_parser)

        # Create sub-parser for managing VM locks
        LockParser(self.subparsers, self.parent_parser)

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
        else:
            raise ArgumentParserException('No handler registered for parser')

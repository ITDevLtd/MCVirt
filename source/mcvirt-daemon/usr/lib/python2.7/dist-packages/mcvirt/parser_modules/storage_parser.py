"""Provides storage management parser."""

# Copyright (c) 2018 - I.T. Dev Ltd
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

from mcvirt.storage.factory import Factory as StorageFactory
from mcvirt.exceptions import ArgumentParserException


class StorageParser(object):
    """Handle storage parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for storage management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create subparser for storage-related commands
        self.parser = self.parent_subparser.add_parser(
            'storage',
            help='Create, modify and delete storage backends',
            parents=[self.parent_parser]
        )
        self.subparser = self.parser.add_subparsers(
            dest='storage_action', metavar='Storage Action',
            help='Action to perform'
        )

        self.register_list()
        self.register_create()
        self.register_delete()
        self.register_add_node()
        self.register_remove_node()

    def register_list(self):
        """Register storage list parser"""
        self.list_parser = self.subparser.add_parser(
            'list',
            help='List storage backends',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)

    def handle_list(self, p_, args):
        """Handle list of storage"""
        storage_factory = p_.rpc.get_connection('storage_factory')
        p_.print_status(storage_factory.list())

    def register_create(self):
        """Register storage create parser"""

        self.create_parser = self.subparser.add_parser(
            'create',
            help='Create storage backend',
            parents=[self.parent_parser])
        self.create_parser.set_defaults(func=self.handle_create)
        self.create_parser.add_argument('Name', help='Name of new storage backend')
        self.create_parser.add_argument(
            '--type',
            dest='storage_type',
            help='Type of backend storage',
            required=True,
            choices=[t.__name__ for t in StorageFactory().get_storage_types()]
        )
        self.create_parser.add_argument(
            '--volume-group-name',
            dest='volume_group_name',
            required=False,
            help=("Name of default volume group for backend storage for nodes \n"
                  '(Required for LVM storage, unless all nodes contain volume group overides)')
        )
        self.create_parser.add_argument(
            '--path',
            dest='path',
            required=False,
            help=("Name of default path for backend storage for nodes \n"
                  '(Required for File storage, unless all nodes contain path overides)')
        )
        self.create_parser.add_argument(
            '--shared',
            dest='shared',
            required=False,
            action='store_true',
            default=False,
            help=('Marks the storage as being shared '
                  'across nodes in the cluster.')
        )
        self.create_parser.add_argument(
            '--node',
            dest='nodes',
            required=False,
            nargs='+',
            action='append',
            default=[],
            help=('Specifies the nodes that this will '
                  "be available to.\n"
                  'Specify once for each node, e.g. '
                  "--node node1 --node node2.\n"
                  'Specify an additional parameter '
                  'to override the path or volume '
                  'group for the node, e.g. '
                  '--node <Node name> '
                  '<Overriden Volume Group/Path> '
                  '--node <Node Name>...')
        )

    def handle_create(self, p_, args):
        """Handle storage create"""
        storage_factory = p_.rpc.get_connection('storage_factory')
        location = None
        if args.storage_type == 'Lvm' and args.volume_group_name:
            location = args.volume_group_name
        elif args.storage_type == 'File' and args.path:
            location = args.path

        # Check length of each node config, to ensure it's not too long
        invalid_nodes = [True if len(n) > 2 else None for n in args.nodes]
        if True in invalid_nodes:
            raise ArgumentParserException(('--node must only be provided with '
                                           'node name and optional storage config '
                                           'override'))

        # Split nodes argument into nodes and storage location overrides
        node_config = {
            node[0]: {'location': node[1] if len(node) == 2 else None}
            for node in args.nodes
        }

        # Add warning for shared/file-based storage
        if args.storage_type == 'File' or args.shared:
            p_.print_status(('WARNING: Shared and file-based storage is a new feature.\n'
                             'Some features may not yet be supported with this type of storage '
                             'and/or maybe unstable.\n'
                             'These issues will be resolved in Release 11.0.0'))

        storage_factory.create(name=args.Name,
                               storage_type=args.storage_type,
                               node_config=node_config,
                               shared=args.shared,
                               location=location)

    def register_delete(self):
        """Register storage deletion parser"""
        self.delete_parser = self.subparser.add_parser(
            'delete',
            help='Delete storage backend',
            parents=[self.parent_parser])
        self.delete_parser.set_defaults(func=self.handle_delete)
        self.delete_parser.add_argument('Name', help='Name of storage backend')

    def handle_delete(self, p_, args):
        """Handle storage deletion"""
        storage_factory = p_.rpc.get_connection('storage_factory')
        storage_backend = storage_factory.get_object_by_name(args.Name)
        p_.rpc.annotate_object(storage_backend)
        storage_backend.delete()

    def register_add_node(self):
        """Register storage add node parser"""
        self.add_node_parser = self.subparser.add_parser(
            'add-node',
            help='Add node to storage backend',
            parents=[self.parent_parser])
        self.add_node_parser.set_defaults(func=self.handle_add_node)
        self.add_node_parser.add_argument('Name', help='Name of storage backend')
        self.add_node_parser.add_argument(
            '--node',
            dest='nodes',
            required=True,
            nargs='+',
            action='append',
            default=[],
            help=('Specifies the node(s) that this will '
                  "be added to the storage backend.\n"
                  'Specify once for each node, e.g. '
                  "--node node1 --node node2.\n"
                  'Specify an additional parameter '
                  'to override the path or volume '
                  'group for the node, e.g. '
                  '--node <Node name> '
                  '<Overriden Volume Group/Path> '
                  '--node <Node Name>...')
        )

    def handle_add_node(self, p_, args):
        """Handle node add to storage"""
        storage_factory = p_.rpc.get_connection('storage_factory')
        storage_backend = storage_factory.get_object_by_name(args.Name)
        p_.rpc.annotate_object(storage_backend)

        # Check lenght of each node config, to ensure it's not too long
        invalid_nodes = [True if len(n) > 2 else None for n in args.nodes]
        if True in invalid_nodes:
            raise ArgumentParserException(('--node must only be provided with '
                                           'node name and optional storage config '
                                           'override'))

        for node in args.nodes:
            storage_backend.add_node(
                node_name=node[0],
                custom_location=(node[1] if len(node) == 2 else None))

    def register_remove_node(self):
        """Register parser to remove node from storage"""
        self.remove_node_parser = self.subparser.add_parser(
            'remove-node',
            help='Add node to storage backend',
            parents=[self.parent_parser])
        self.remove_node_parser.set_defaults(func=self.handle_remove_node)
        self.remove_node_parser.add_argument('Name', help='Name of storage backend')
        self.remove_node_parser.add_argument(
            '--node',
            dest='nodes',
            required=True,
            action='append',
            default=[],
            help='Specifies the node(s) that will be removed from the storage backend'
        )

    def handle_remove_node(self, p_, args):
        """Hanlde remove of node from storage"""
        storage_factory = p_.rpc.get_connection('storage_factory')
        storage_backend = storage_factory.get_object_by_name(args.Name)
        p_.rpc.annotate_object(storage_backend)

        for node in args.nodes:
            storage_backend.remove_node(node_name=node)

"""Provides cluster management parser."""

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

from mcvirt.system import System


class ClusterParser(object):
    """Handle cluster parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for cluster management."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for cluster-related commands
        self.parser = self.parent_subparser.add_parser(
            'cluster',
            help='Manage an MCVirt cluster and the connected nodes',
            parents=[self.parent_parser]
        )
        self.subparser = self.parser.add_subparsers(
            dest='cluster_action',
            metavar='Action',
            help='Action to perform on the cluster'
        )

        self.register_get_connect_string()
        self.register_add()
        self.register_remove()

    def register_get_connect_string(self):
        """Register get connect string parser."""
        self.connection_string_subparser = self.subparser.add_parser(
            'get-connect-string',
            help='Generates a connection string to add the node to a cluster',
            parents=[self.parent_parser]
        )
        self.connection_string_subparser.set_defaults(
            func=self.handle_get_connect_string)

    def handle_get_connect_string(self, p_, args):
        """Handle get connection string."""
        cluster_object = p_.rpc.get_connection('cluster')
        p_.print_status(cluster_object.get_connection_string())

    def register_add(self):
        """Register node add parser."""
        self.node_add_parser = self.subparser.add_parser(
            'add-node',
            help='Adds a node to the MCVirt cluster',
            parents=[self.parent_parser])
        self.node_add_parser.set_defaults(func=self.handle_add)
        self.node_add_parser.add_argument(
            '--connect-string',
            dest='connect_string',
            metavar='node',
            type=str,
            required=True,
            help='Connect string from the target node')

    def handle_add(self, p_, args):
        """Handle add of node."""
        cluster_object = p_.rpc.get_connection('cluster')
        if args.connect_string:
            connect_string = args.connect_string
        else:
            connect_string = System.getUserInput('Enter Connect String: ')
        cluster_object.add_node(connect_string)
        p_.print_status('Successfully added node')

    def register_remove(self):
        """Register parser for removing node."""
        self.node_remove_parser = self.subparser.add_parser(
            'remove-node',
            help='Removes a node to the MCVirt cluster',
            parents=[self.parent_parser]
        )
        self.node_remove_parser.set_defaults(func=self.handle_remove)
        self.node_remove_parser.add_argument(
            '--node',
            dest='node',
            metavar='node',
            type=str,
            required=True,
            help='Hostname of the remote node to remove from the cluster')

    def handle_remove(self, p_, args):
        """Handle remove node."""
        cluster_object = p_.rpc.get_connection('cluster')
        cluster_object.remove_node(args.node)
        p_.print_status('Successfully removed node %s' % args.node)

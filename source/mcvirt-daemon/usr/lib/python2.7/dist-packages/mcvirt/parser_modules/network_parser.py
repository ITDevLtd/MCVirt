"""Provides network management parser."""

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


class NetworkParser(object):
    """Handle network parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for network management."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create subparser for network-related commands
        self.parser = self.parent_subparser.add_parser(
            'network',
            help='Manage the virtual networks on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.subparser = self.parser.add_subparsers(
            dest='network_action',
            metavar='Action',
            help='Action to perform on the network'
        )

        self.register_list()
        self.register_create()
        self.register_delete()

    def register_list(self):
        """Register network list parser."""
        self.list_parser = self.subparser.add_parser('list', help='List the networks on the node',
                                                     parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)

    def handle_list(self, p_, args):
        """Handle network listing."""
        network_factory = p_.rpc.get_connection('network_factory')
        p_.print_status(network_factory.get_network_list_table())

    def register_create(self):
        """Register parser to handle network creation."""
        self.create_parser = self.subparser.add_parser(
            'create',
            help='Create a network on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.create_parser.set_defaults(func=self.handle_create)
        self.create_parser.add_argument(
            '--interface',
            dest='interface',
            metavar='Interface',
            type=str,
            required=True,
            help='Physical interface on the system to bridge to the virtual network'
        )
        self.create_parser.add_argument('network', metavar='Network Name', type=str,
                                        help='Name of the virtual network to be created')

    def handle_create(self, p_, args):
        """Handle network creation."""
        network_factory = p_.rpc.get_connection('network_factory')
        network_factory.create(args.network, physical_interface=args.interface)

    def register_delete(self):
        """Register parser to handle network deletions."""
        self.delete_parser = self.subparser.add_parser(
            'delete',
            help='Delete a network on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.delete_parser.set_defaults(func=self.handle_delete)
        self.delete_parser.add_argument('network', metavar='Network Name', type=str,
                                        help='Name of the virtual network to be removed')

    def handle_delete(self, p_, args):
        """Handle network deletion."""
        network_factory = p_.rpc.get_connection('network_factory')
        network_object = network_factory.get_network_by_name(args.network)
        p_.rpc.annotate_object(network_object)
        network_object.delete()

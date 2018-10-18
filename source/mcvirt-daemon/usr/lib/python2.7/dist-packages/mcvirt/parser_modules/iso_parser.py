"""Provides ISO argument parser."""

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

import binascii

from mcvirt.exceptions import ArgumentParserException


class IsoParser(object):
    """Handle ISO parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for ISO management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        self.parser = self.parent_subparser.add_parser(
            'iso',
            help='ISO management',
            parents=[self.parent_parser]
        )

        self.sub_parsers = self.parser.add_subparsers(
            dest='iso_action', metavar='ISO Action',
            help='Action to perform'
        )

        self.register_list()
        self.register_add()
        self.register_delete()

    def register_list(self):
        """Register parser for listing ISOs"""
        self.list_parser = self.sub_parsers.add_parser(
            'list',
            help='List available ISOs',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)
        self.list_parser.add_argument('--node', dest='iso_node',
                                      help='Specify the node to perform the action on',
                                      metavar='Node', default=None)

    def handle_list(self, p_, args):
        """Perform list of groups"""
        iso_factory = p_.rpc.get_connection('iso_factory')
        p_.print_status(iso_factory.get_iso_list(node=args.iso_node))

    def register_add(self):
        """Register parser for adding iso"""
        self.add_parser = self.sub_parsers.add_parser(
            'add', help='Add an ISO', parents=[self.parent_parser])
        self.add_parser.set_defaults(func=self.handle_add)
        self.add_parser.add_argument('iso_name', metavar='ISO', type=str,
                                     help='Path/URL of ISO to add')

        self.add_iso_methods = self.add_parser.add_mutually_exclusive_group(required=True)
        self.add_iso_methods.add_argument('--from-path', dest='add_path', action='store_true',
                                          help='Copy an ISO to ISO directory')
        self.add_iso_methods.add_argument('--from-url', dest='add_url', action='store_true',
                                          help='Download and add an ISO')
        self.add_parser.add_argument('--node', dest='iso_node',
                                     help='Specify the node to perform the action on',
                                     metavar='Node', default=None)

    def handle_add(self, p_, args):
        """Handle add of ISO"""
        iso_factory = p_.rpc.get_connection('iso_factory')

        if args.add_path:
            if args.iso_node:
                raise ArgumentParserException('Cannot add to remote node from local path')
            iso_writer = iso_factory.add_iso_from_stream(args.iso_name)
            p_.rpc.annotate_object(iso_writer)
            with open(args.iso_name, 'rb') as iso_fh:
                while True:
                    data_chunk = iso_fh.read(1024)
                    if data_chunk:
                        data_chunk = binascii.hexlify(data_chunk)
                        iso_writer.write_data(data_chunk)
                    else:
                        break
            iso_object = iso_writer.write_end()
            p_.rpc.annotate_object(iso_object)
            p_.print_status('Successfully added ISO: %s' % iso_object.get_name())

        if args.add_url:
            iso_name = iso_factory.add_from_url(args.iso_name, node=args.iso_node)
            p_.print_status('Successfully added ISO: %s' % iso_name)

    def register_delete(self):
        """Register parser for deleting ISOs"""
        self.delete_parser = self.sub_parsers.add_parser(
            'delete', help='Delete an ISO', parents=[self.parent_parser])
        self.delete_parser.set_defaults(func=self.handle_delete)
        self.delete_parser.add_argument('delete_path', metavar='NAME', type=str,
                                        help='ISO to delete')
        self.delete_parser.add_argument('--node', dest='iso_node',
                                        help='Specify the node to perform the action on',
                                        metavar='Node', default=None)

    def handle_delete(self, p_, args):
        """Handle deletion of ISO"""
        iso_factory = p_.rpc.get_connection('iso_factory')
        if args.iso_node:
            raise ArgumentParserException('Cannot remove ISO from remote node')
        iso_object = iso_factory.get_iso_by_name(args.delete_path)
        p_.rpc.annotate_object(iso_object)
        iso_object.delete()
        p_.print_status('Successfully removed iso: %s' % args.delete_path)

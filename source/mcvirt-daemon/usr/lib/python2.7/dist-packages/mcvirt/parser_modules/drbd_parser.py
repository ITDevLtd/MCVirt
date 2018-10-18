"""Provides Drbd management parser parser."""

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


class DrbdParser(object):
    """Handle DRBD management parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for DRBD management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for Drbd-related commands
        self.parser = self.parent_subparser.add_parser(
            'drbd', help='Manage Drbd clustering', parents=[self.parent_parser])
        self.subparser = self.parser.add_subparsers(dest='drbd_action', metavar='Action',
                                                    help='Drbd action to perform')

        self.register_enable()
        self.register_list()

    def register_enable(self):
        """Register enable parser"""
        self.enable_parser = self.subparser.add_parser(
            'enable', help='Enable Drbd support on the cluster',
            parents=[self.parent_parser])
        self.enable_parser.set_defaults(func=self.handle_enable)

    def handle_enable(self, p_, args):
        """Handle DRBD enable"""
        node_drbd = p_.rpc.get_connection('node_drbd')
        node_drbd.enable()
        p_.print_status('Successfully enabled DRBD')

    def register_list(self):
        """Register DRBD list parser"""
        self.list_parser = self.subparser.add_parser(
            'list', help='List Drbd volumes on the system',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)

    def handle_list(self, p_, args):
        """Handle DRBD list"""
        node_drbd = p_.rpc.get_connection('node_drbd')
        p_.print_status(node_drbd.list())

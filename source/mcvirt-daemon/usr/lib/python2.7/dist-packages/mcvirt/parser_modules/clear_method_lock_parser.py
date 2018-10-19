"""Provides clear method lock argument parser."""

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


class ClearMethodLockParser(object):
    """Handle clear method lock parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for clearing method lock"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        self.method_lock_parser = self.parent_subparser.add_parser(
            'clear-method-lock',
            help='Resolve the lock of a call to a method on the MCVirt daemon.',
            parents=[self.parent_parser]
        )
        self.method_lock_parser.set_defaults(func=self.handle_clear_method_lock)

    def handle_clear_method_lock(self, p_, args):
        """Handle method lock clear"""
        node = p_.rpc.get_connection('node')
        if node.clear_method_lock():
            p_.print_status('Successfully cleared method lock')
        else:
            p_.print_status('Method lock already cleared')

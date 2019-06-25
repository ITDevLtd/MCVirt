"""Provides VM duplicate parser."""

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


class DuplicateParser(object):
    """Handle VM duplicate parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for VM duplicate."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for cloning a VM
        self.duplicate_parser = self.parent_subparser.add_parser(
            'duplicate', help='Duplicate a VM', parents=[self.parent_parser])
        self.duplicate_parser.set_defaults(func=self.handle_duplicate)
        self.duplicate_parser.add_argument('--template', dest='template', metavar='Parent VM',
                                           type=str, required=True,
                                           help='The name of the VM to duplicate')
        self.duplicate_parser.add_argument('--retain-mac-address',
                                           help='Retain MAC address from clones',
                                           dest='retain_mac', action='store_true')
        self.duplicate_parser.add_argument('vm_name', metavar='VM Name', type=str,
                                           help='Name of duplicate VM')

    def handle_duplicate(self, p_, args):
        """Handle VM duplication."""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.template)
        p_.rpc.annotate_object(vm_object)
        vm_object.duplicate(args.vm_name, retain_mac=args.retain_mac)

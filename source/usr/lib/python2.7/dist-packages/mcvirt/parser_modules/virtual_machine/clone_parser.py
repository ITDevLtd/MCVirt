"""Provides VM clone parser."""

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


class CloneParser(object):
    """Handle VM clone parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for VM clone"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for cloning a VM
        self.clone_parser = self.parent_subparser.add_parser(
            'clone', help='Clone a VM', parents=[self.parent_parser])
        self.clone_parser.set_defaults(func=self.handle_clone)
        self.clone_parser.add_argument('--template', dest='template', type=str,
                                       required=True, metavar='Parent VM',
                                       help='The name of the VM to clone from')
        self.clone_parser.add_argument('--retain-mac-address',
                                       help='Retain MAC address from clones',
                                       dest='retain_mac', action='store_true')
        self.clone_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

    def handle_clone(self, p_, args):
        """Handle VM clone"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.getVirtualMachineByName(args.template)
        p_.rpc.annotate_object(vm_object)
        vm_object.clone(args.vm_name, retain_mac=args.retain_mac)

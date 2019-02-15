"""Provides VM move parser."""

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


class MoveParser(object):
    """Handle VM move parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for VM move"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for moving VMs
        self.move_parser = self.parent_subparser.add_parser(
            'move', help='Move a VM and related storage to another node',
            parents=[self.parent_parser])
        self.move_parser.set_defaults(func=self.handle_move)
        self.move_parser.add_argument('--source-node', dest='source_node',
                                      help="The node that the VM will be moved from.\n" +
                                      'For Drbd VMs, the source node must not be' +
                                      " the local node.\nFor Local VMs, the node" +
                                      " must be the local node, but may be omitted.")
        self.move_parser.add_argument('--destination-node', dest='destination_node',
                                      help='The node that the VM will be moved to')
        self.move_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

    def handle_move(self, p_, args):
        """handle VM move"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        vm_object.move(destination_node=args.destination_node,
                       source_node=args.source_node)

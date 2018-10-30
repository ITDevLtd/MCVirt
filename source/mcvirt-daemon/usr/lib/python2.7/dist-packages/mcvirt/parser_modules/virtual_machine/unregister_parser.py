"""Provides VM un-register parser."""

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


class UnregisterParser(object):
    """Handle VM un-register parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for unregistering VMs"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for unregistering a VM
        self.unregister_parser = self.parent_subparser.add_parser(
            'unregister', help='Unregisters a VM on the local node',
            parents=[self.parent_parser])
        self.unregister_parser.set_defaults(func=self.handle_unregister)
        self.unregister_parser.add_argument('vm_name', metavar='VM Name', type=str,
                                            help='Name of VM')

    def handle_unregister(self, p_, args):
        """Handle unregister"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        vm_object.unregister()

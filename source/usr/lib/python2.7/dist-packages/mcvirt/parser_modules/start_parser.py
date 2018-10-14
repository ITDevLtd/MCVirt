"""Provides VM start parser."""

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


class StartParser(object):
    """Handle VM start parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for shutting down VMs"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Add arguments for starting a VM
        self.start_parser = self.parent_subparser.add_parser(
            'start', help='Start VM', parents=[self.parent_parser])
        self.start_parser.add_argument('--iso', metavar='ISO Name', type=str,
                                       help='Path of ISO to attach to VM', default=None)
        self.start_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                       help='Names of VMs')
        self.start_parser.set_defaults(func=self.handle_start)

    def handle_start(self, p_, args):
        """Handle start"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        for vm_name in args.vm_names:
            try:
                vm_object = vm_factory.getVirtualMachineByName(vm_name)
                p_.rpc.annotate_object(vm_object)
                vm_object.start(iso_name=args.iso)
                p_.print_status('Successfully started VM %s' % vm_name)
            except Exception:
                p_.print_status('Error while starting VM %s' % vm_name)
                raise

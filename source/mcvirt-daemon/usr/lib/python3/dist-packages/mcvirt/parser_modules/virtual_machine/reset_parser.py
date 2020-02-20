"""Provides VM reset parser."""

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


class ResetParser(object):
    """Handle VM reset parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for resetting VMs."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Add arguments for resetting a VM
        self.reset_parser = self.parent_subparser.add_parser(
            'reset', help='Reset VM',
            parents=[self.parent_parser])
        self.reset_parser.set_defaults(func=self.handle_reset)
        self.reset_parser.add_argument('vm_names', nargs='*', metavar='VM Names', type=str,
                                       help='Names of VMs')

    def handle_reset(self, p_, args):
        """Handle reset."""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        for vm_name in args.vm_names:
            try:
                vm_object = vm_factory.get_virtual_machine_by_name(vm_name)
                p_.rpc.annotate_object(vm_object)
                vm_object.reset()
                p_.print_status('Successfully reset VM %s' % vm_name)
            except Exception:
                p_.print_status('Error while resetting VM %s' % vm_name)
                raise

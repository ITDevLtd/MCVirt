"""Provides VM delete parser."""

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

from argparse import SUPPRESS


class DeleteParser(object):
    """Handle VM delete parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for deleting VMs."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for deleting a VM
        self.delete_parser = self.parent_subparser.add_parser(
            'delete', help='Delete VM', parents=[self.parent_parser])
        self.delete_parser.set_defaults(func=self.handle_delete)

        # This argument is deprecated, this is now default functionality, replaced
        # with --keep-data and --keep-config
        self.delete_parser.add_argument('--delete-data', dest='delete_data', action='store_true',
                                        help=SUPPRESS)
        self.delete_parser.add_argument('--keep-config', dest='keep_config', action='store_true',
                                        help=('Keeps the VM configuration directory\n'
                                              'Note: A new VM cannot be created with '
                                              'the same name until this directory '
                                              'is removed'))
        self.delete_parser.add_argument('--keep-disks', dest='keep_disks', action='store_true',
                                        help=('Keeps the VM hard drives '
                                              '(files on disk or logical volume)\n'
                                              'Note: A new VM cannot be created with '
                                              'the same name until this directory '
                                              'is removed'))
        self.delete_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

    def handle_delete(self, p_, args):
        """Handle delete."""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        vm_object.delete(keep_disks=args.keep_disks,
                         keep_config=args.keep_config)

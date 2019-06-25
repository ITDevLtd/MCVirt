"""Provides resync argument parser."""

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


class ResyncParser(object):
    """Handle resync parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for disk resync."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for VM disk resync
        self.parser = self.parent_subparser.add_parser(
            'resync',
            help='Perform resync of DRBD volumes',
            parents=[self.parent_parser])
        self.parser.set_defaults(func=self.handle_resync)
        self.resync_node_mutual_exclusive_group = self.parser.add_mutually_exclusive_group(
            required=True
        )
        self.resync_node_mutual_exclusive_group.add_argument(
            '--source-node', dest='resync_node', default=None,
            help='Specify the SOURCE node for the resync.'
        )
        self.resync_node_mutual_exclusive_group.add_argument(
            '--auto-determine', dest='resync_auto_determine', action='store_true',
            help='Automatically sync from the node that the VM is currently registered on.'
        )
        self.parser.add_argument('vm_name', metavar='VM Name',
                                 help='Specify a single VM to resync')
        self.parser.add_argument('--disk-id', metavar='Disk Id', default=1, type=int,
                                 help='Specify the Disk ID to resync (default: 1)')

    def handle_resync(self, p_, args):
        """Handle resync."""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        hard_drive_attachment_factory = p_.rpc.get_connection('hard_drive_attachment_factory')
        hard_drive_object = hard_drive_attachment_factory.get_object(
            vm_object, args.disk_id).get_hard_drive_object()
        p_.rpc.annotate_object(hard_drive_object)
        hard_drive_object.resync(source_node=args.resync_node,
                                 auto_determine=args.resync_auto_determine)

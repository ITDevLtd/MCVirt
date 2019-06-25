"""Provides VM info parser."""

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


class InfoParser(object):
    """Handle VM info parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for getting VM info."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for getting VM information
        self.info_parser = self.parent_subparser.add_parser(
            'info', help='View VM information',
            parents=[self.parent_parser])
        self.info_parser.set_defaults(func=self.handle_info)
        self.info_mutually_exclusive_group = self.info_parser.add_mutually_exclusive_group(
            required=False
        )
        self.info_mutually_exclusive_group.add_argument(
            '--vnc-port',
            dest='vnc_port',
            help='Displays the port that VNC is being hosted from',
            action='store_true'
        )
        self.info_mutually_exclusive_group.add_argument(
            '--node',
            dest='node',
            help='Displays which node that the VM is currently registered on',
            action='store_true'
        )
        self.info_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM',
                                      nargs='?', default=None)

    def handle_info(self, p_, args):
        """Handle info function."""
        if not args.vm_name and (args.vnc_port or args.node):
            p_.parser.error('Must provide a VM Name')
        if args.vm_name:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
            p_.rpc.annotate_object(vm_object)
            if args.vnc_port:
                p_.print_status(vm_object.getVncPort())
            elif args.node:
                p_.print_status(vm_object.getNode())
            else:
                p_.print_status(vm_object.getInfo())
        else:
            cluster_object = p_.rpc.get_connection('cluster')
            p_.print_status(cluster_object.print_info())

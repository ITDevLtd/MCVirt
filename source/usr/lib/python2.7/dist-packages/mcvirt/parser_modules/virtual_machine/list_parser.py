"""Provides VM list parser."""

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


class ListParser(object):
    """Handle VM list parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for VM list"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for listing VMs
        self.list_parser = self.parent_subparser.add_parser(
            'list', help='List VMs present on host',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)
        self.list_parser.add_argument('--cpu', dest='include_cpu', help='Include CPU column',
                                      action='store_true')
        self.list_parser.add_argument('--memory', '--ram', dest='include_ram',
                                      help='Include RAM column', action='store_true')
        self.list_parser.add_argument('--disk-size', '--hdd', dest='include_disk',
                                      help='Include HDD column', action='store_true')

    def handle_list(self, p_, args):
        """Handle VM listing"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        p_.print_status(vm_factory.listVms(include_cpu=args.include_cpu,
                                           include_ram=args.include_ram,
                                           include_disk=args.include_disk))

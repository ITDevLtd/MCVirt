"""Provides watchdog management parser parser."""

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


class WatchdogParser(object):
    """Handle watchdog management parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for watchdog management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for Drbd-related commands
        self.parser = self.parent_subparser.add_parser(
            'watchdog', help='Manage watchdog', parents=[self.parent_parser])
        self.subparser = self.parser.add_subparsers(dest='watchdog_action', metavar='Action',
                                                    help='Watchdog action to perform')

        self.register_enable()
        self.register_disable()

    def register_enable(self):
        """Register enable parser"""
        self.enable_parser = self.subparser.add_parser(
            'enable', help='Enable watchdog on a VM',
            parents=[self.parent_parser])
        self.enable_parser.add_argument('vm_name', metavar='VM Name')
        self.enable_parser.set_defaults(func=self.handle_enable)

    def handle_enable(self, p_, args):
        """Handle watchdog enable"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm = vm_factory.getVirtualMachineByName(args.vm_name)
        p_.rpc.annotate_object(vm)
        vm.set_watchdog_status(True)
        p_.print_status('Successfully enabled watchdog for VM: %s' % vm.get_name())

    def register_disable(self):
        """Register disable parser"""
        self.disable_parser = self.subparser.add_parser(
            'disable', help='Disable watchdog on a VM',
            parents=[self.parent_parser])
        self.disable_parser.add_argument('vm_name', metavar='VM Name')
        self.disable_parser.set_defaults(func=self.handle_disable)

    def handle_disable(self, p_, args):
        """Handle disable watchdog"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm = vm_factory.getVirtualMachineByName(args.vm_name)
        p_.rpc.annotate_object(vm)
        vm.set_watchdog_status(False)
        p_.print_status('Successfully disabled watchdog for VM: %s' % vm.get_name())

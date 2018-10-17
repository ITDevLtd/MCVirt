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
        self.subparser = self.parser.add_subparsers(
            dest='watchdog_action',
            metavar='Action',
            help='Watchdog action to perform')

        self.register_enable()
        self.register_disable()
        self.register_set_interval()
        self.register_set_reset_fail_count()
        self.register_set_boot_wait()

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
        virtual_machine = vm_factory.getVirtualMachineByName(args.vm_name)
        p_.rpc.annotate_object(virtual_machine)
        virtual_machine.set_watchdog_status(True)
        p_.print_status('Successfully enabled watchdog for VM: %s' % virtual_machine.get_name())

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
        virtual_machine = vm_factory.getVirtualMachineByName(args.vm_name)
        p_.rpc.annotate_object(virtual_machine)
        virtual_machine.set_watchdog_status(False)
        p_.print_status('Successfully disabled watchdog for VM: %s' % virtual_machine.get_name())

    def register_set_interval(self):
        """Register set interval parser"""
        self.interval_parser = self.subparser.add_parser(
            'set-interval', help=('Set watchdog check interval '
                                  '(either the global default or per VM)'),
            parents=[self.parent_parser])
        self.interval_mut_group = self.interval_parser.add_mutually_exclusive_group(
            required=True
        )
        self.interval_mut_group.add_argument('--interval', metavar='Interval (seconds)')
        self.interval_mut_group.add_argument('--inherit', dest='inherit_global',
                                             help='Set VM to inherit from global config',
                                             action='store_true')
        self.interval_parser.add_argument('--virtual-machine-name', '--vm-name',
                                          default=None, dest='vm_name', metavar='VM Name')
        self.interval_parser.set_defaults(func=self.handle_set_interval)

    def handle_set_interval(self, p_, args):
        """Handle set watchdog interval"""
        if args.vm_name is None:
            watchdog_factory = p_.rpc.get_connection('watchdog_factory')
            watchdog_factory.set_global_interval(args.interval)
            p_.print_status('Set global default watchdog interval to %s' % args.interval)
        else:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            virtual_machine = vm_factory.getVirtualMachineByName(args.vm_name)
            p_.rpc.annotate_object(virtual_machine)
            interval = None if args.inherit_global else args.interval
            virtual_machine.set_watchdog_interval(interval)
            if interval is None:
                p_.print_status(
                    'Set watchdog interval to inherit global for VM: %s' %
                    virtual_machine.get_name())
            else:
                p_.print_status(
                    'Set watchdog interval to %s for VM: %s' %
                    (args.interval, virtual_machine.get_name()))

    def register_set_reset_fail_count(self):
        """Register set reset fail count parser"""
        self.reset_fail_count_parser = self.subparser.add_parser(
            'set-reset-fail-count',
            help=('Set number for watchdog failures before a VM is reset '
                  '(either the global default or per VM)'),
            parents=[self.parent_parser])
        self.reset_fail_mut_group = self.reset_fail_count_parser.add_mutually_exclusive_group(
            required=True
        )
        self.reset_fail_mut_group.add_argument('--count', metavar='Count (number of failures)',
                                               dest='count')
        self.reset_fail_mut_group.add_argument('--inherit', dest='inherit_global',
                                               help='Set VM to inherit from global config',
                                               action='store_true')
        self.reset_fail_count_parser.add_argument('--virtual-machine-name', '--vm-name',
                                                  default=None, dest='vm_name', metavar='VM Name')
        self.reset_fail_count_parser.set_defaults(func=self.handle_set_reset_fail_count)

    def handle_set_reset_fail_count(self, p_, args):
        """Handle set watchdog reset fail count"""
        if args.vm_name is None:
            watchdog_factory = p_.rpc.get_connection('watchdog_factory')
            watchdog_factory.set_global_reset_fail_count(args.count)
            p_.print_status('Set global default reset fail count to %s' % args.count)
        else:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            virtual_machine = vm_factory.getVirtualMachineByName(args.vm_name)
            p_.rpc.annotate_object(virtual_machine)
            count = None if args.inherit_global else args.count
            virtual_machine.set_watchdog_reset_fail_count(count)
            if count is None:
                p_.print_status(
                    'Set watchdog reset fail count to inherit global for VM: %s' %
                    virtual_machine.get_name())
            else:
                p_.print_status(
                    'Set watchdog reset fail count to %s for VM: %s' %
                    (args.count, virtual_machine.get_name()))

    def register_set_boot_wait(self):
        """Register set boot wait period parser"""
        self.boot_wait_parser = self.subparser.add_parser(
            'set-boot-wait', help=('Set grace period during VM boot before watchdog starts '
                                   '(either the global default or per VM)'),
            parents=[self.parent_parser])
        self.boot_wait_mut_group = self.boot_wait_parser.add_mutually_exclusive_group(
            required=True
        )
        self.boot_wait_mut_group.add_argument('--time', '--wait-time',
                                              metavar='Boot wait period (seconds)')
        self.boot_wait_mut_group.add_argument('--inherit', dest='inherit_global',
                                              help='Set VM to inherit from global config',
                                              action='store_true')
        self.boot_wait_parser.add_argument('--virtual-machine-name', '--vm-name',
                                           default=None, dest='vm_name', metavar='VM Name')
        self.boot_wait_parser.set_defaults(func=self.handle_set_boot_wait)

    def handle_set_boot_wait(self, p_, args):
        """Handle set watchdog interval"""
        if args.vm_name is None:
            watchdog_factory = p_.rpc.get_connection('watchdog_factory')
            watchdog_factory.set_global_boot_wait(args.time)
            p_.print_status('Set global default watchdog boot wait period to %s' % args.time)
        else:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            virtual_machine = vm_factory.getVirtualMachineByName(args.vm_name)
            p_.rpc.annotate_object(virtual_machine)
            wait_time = None if args.inherit_global else args.time
            virtual_machine.set_watchdog_boot_wait(wait_time)
            if wait_time is None:
                p_.print_status(
                    'Set watchdog boot wait period to inherit global for VM: %s' %
                    virtual_machine.get_name())
            else:
                p_.print_status(
                    'Set watchdog bot wait period to %s for VM: %s' %
                    (wait_time, virtual_machine.get_name()))

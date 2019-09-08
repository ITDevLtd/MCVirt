"""Provides VM migration parser."""

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


class MigrateParser(object):
    """Handle VM migration parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for VM migration."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for migrating a VM
        self.migrate_parser = self.parent_subparser.add_parser(
            'migrate',
            help='Perform migrations of virtual machines',
            parents=[self.parent_parser]
        )
        self.migrate_parser.set_defaults(func=self.handle_migrate)
        self.migrate_parser.add_argument(
            '--node',
            dest='destination_node',
            metavar='Destination Node',
            type=str,
            required=True,
            help='The name of the destination node for the VM to be migrated to'
        )
        self.migrate_parser.add_argument(
            '--online',
            dest='online_migration',
            help='Perform an online-migration',
            action='store_true'
        )
        self.migrate_parser.add_argument(
            '--start-after-migration',
            dest='start_after_migration',
            help='Causes the VM to be booted after the migration',
            action='store_true'
        )
        self.migrate_parser.add_argument(
            '--wait-for-shutdown',
            dest='wait_for_shutdown',
            help='Waits for the VM to shutdown before performing the migration',
            action='store_true'
        )
        self.migrate_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

    def handle_migrate(self, p_, args):
        """Handle migration."""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        if args.online_migration:
            vm_object.online_migrate(args.destination_node)
        else:
            vm_object.offline_migrate(
                args.destination_node,
                wait_for_vm_shutdown=args.wait_for_shutdown,
                start_after_migration=args.start_after_migration
            )
        p_.print_status('Successfully migrated \'%s\' to %s' %
                        (vm_object.get_name(), args.destination_node))

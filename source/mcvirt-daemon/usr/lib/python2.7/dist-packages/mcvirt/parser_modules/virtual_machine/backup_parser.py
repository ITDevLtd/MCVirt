"""Provides backup management parser parser."""

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


class BackupParser(object):
    """Handle backup management parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for backup management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for backup commands
        self.parser = self.parent_subparser.add_parser(
            'backup', help='Performs backup-related tasks', parents=[self.parent_parser])
        self.subparser = self.parser.add_subparsers(
            dest='backup_action',
            metavar='Action',
            help='Backup action to perform'
        )

        self.register_create_snapshot()
        self.register_delete_snapshot()

    def register_create_snapshot(self):
        """Register create snapshot parser"""
        self.create_snapshot_parser = self.subparser.add_parser(
            'create-snapshot',
            help='Create a snapshot of the specified disk',
            parents=[self.parent_parser]
        )
        self.create_snapshot_parser.set_defaults(func=self.handle_create_snapshot)
        self.create_snapshot_parser.add_argument(
            '--disk-id', dest='disk_id', metavar='Disk Id', type=int, required=True,
            help='The ID of the disk to manage the backup snapshot of'
        )

    def handle_create_snapshot(self, p_, args):
        """Handle create snapshot"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
        p_.rpc.annotate_object(hard_drive_object)
        p_.print_status(hard_drive_object.create_backup_snapshot())

    def register_delete_snapshot(self):
        """Register delete snapshot parser"""
        self.delete_snapshot_parser = self.subparser.add_parser(
            'delete-snapshot',
            help='Delete the snapshot of the specified disk',
            parents=[self.parent_parser]
        )
        self.delete_snapshot_parser.set_defaults(func=self.handle_delete_snapshot)
        self.delete_snapshot_parser.add_argument(
            '--disk-id', dest='disk_id', metavar='Disk Id', type=int, required=True,
            help='The ID of the disk to manage the backup snapshot of'
        )

    def handle_delete_snapshot(self, p_, args):
        """Handle delete snapshot"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        hard_drive_object = hard_drive_factory.getObject(vm_object, args.disk_id)
        hard_drive_object.delete_backup_snapshot()

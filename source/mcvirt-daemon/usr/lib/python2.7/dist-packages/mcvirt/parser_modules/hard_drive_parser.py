"""Provides hard drive parser."""

# Copyright (c) 2018 - Matt Comben
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


class HardDriveParser(object):
    """Handle hard drive parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for hard rive management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create subparser for network-related commands
        self.parser = self.parent_subparser.add_parser(
            'hard-drive',
            help='Manage the virtual hard drives on the MCVirt host',
            parents=[self.parent_parser]
        )
        self.subparser = self.parser.add_subparsers(
            dest='hard_drive_action',
            metavar='Action',
            help='Action to perform on hard drive'
        )

        self.register_list()
        self.register_attach()
        self.register_detach()
        self.register_import()

    def register_list(self):
        """Register network list parser"""
        self.list_parser = self.subparser.add_parser(
            'list', help='List the hard drives on the node',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)

    def handle_list(self, p_, args):
        """Handle network listing"""
        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        p_.print_status(hard_drive_factory.get_hard_drive_list_table())

    def register_attach(self):
        """Register parser to handle network creation"""
        self.attach_parser = self.subparser.add_parser(
            'attach',
            help='Attach a hard drive to a virtual machine',
            parents=[self.parent_parser]
        )
        self.attach_parser.set_defaults(func=self.handle_attach)
        self.attach_parser.add_argument(
            'hard_drive_id', metavar='Hard Drive Id', type=str,
            help='ID of the hard drive to be attached to the virtual machine')
        self.attach_parser.add_argument(
            'virtual_machine_name', metavar='Virtual Machine name', type=str,
            help='Name of the virtual machine')

    def handle_attach(self, p_, args):
        """Handle network creation"""
        virtual_machine_factory = p_.rpc.get_connection('virtual_machine_factory')
        virtual_machine = virtual_machine_factory.get_virtual_machine_by_name(
            args.virtual_machine_name)
        p_.rpc.annotate_object(virtual_machine)

        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        hard_drive = hard_drive_factory.get_object(args.hard_drive_id)
        p_.rpc.annotate_object(hard_drive)

        hard_drive_attachment_factory = p_.rpc.get_connection('hard_drive_attachment_factory')
        hard_drive_attachment_factory.create(virtual_machine, hard_drive)

    def register_detach(self):
        """Register parser to handle hard drive detaching from VM"""
        self.detach_parser = self.subparser.add_parser(
            'detach',
            help='Detach a hard drive from a virtual machine',
            parents=[self.parent_parser]
        )
        self.detach_parser.set_defaults(func=self.handle_detach)
        self.detach_parser.add_argument(
            'hard_drive_id', metavar='Hard Drive Id', type=str,
            help='ID of the hard drive to be detached from virtual machine')

    def handle_detach(self, p_, args):
        """Handle hard drive detach"""
        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        hard_drive = hard_drive_factory.get_object(args.hard_drive_id)
        p_.rpc.annotate_object(hard_drive)

        hard_drive_attachment_factory = p_.rpc.get_connection('hard_drive_attachment_factory')
        attachment = hard_drive_attachment_factory.get_object_by_hard_drive(
            hard_drive, raise_on_failure=True)
        p_.rpc.annotate_object(attachment)
        attachment.delete()

    def register_import(self):
        """Register parser to import hard drive"""
        self.import_parser = self.subparser.add_parser(
            'import',
            help=('Import a hard drive into MCVirt. '
                  'Note: This only works for \'Local\'-based hard drives'),
            parents=[self.parent_parser]
        )
        self.import_parser.set_defaults(func=self.handle_import)
        self.import_parser.add_argument(
            'volume_name', metavar='Volume Name', type=str,
            help=('Name of volume (within the storage backend,'
                  ' e.g. logical volume name or raw filename)'))
        self.import_parser.add_argument(
            'storage_backend_id', metavar='Storage Backend ID', type=str,
            help='Storage backend ID that the hard drive is in')
        self.import_parser.add_argument(
            '--virtual-machine',
            metavar='Virtual Machine Name', type=str,
            help='Name of the virtual machine to attach the new hard drive to (optional)',
            required=False, default=None)

    def handle_import(self, p_, args):
        """Perform hard drive import"""
        if args.virtual_machine:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            virtual_machine = vm_factory.get_virtual_machine_by_name(args.virtual_machine)
            p_.rpc.annotate_object(virtual_machine)
        else:
            virtual_machine = None

        storage_factory = p_.rpc.get_connection('storage_factory')
        storage_backend = storage_factory.get_object(args.storage_backend_id)
        p_.rpc.annotate_object(storage_backend)

        hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
        hdd_object = hard_drive_factory.import_(
            base_volume_name=args.volume_name,
            storage_backend=storage_backend,
            virtual_machine=virtual_machine)
        p_.rpc.annotate_object(hdd_object)
        p_.print_status('Created hard drive: %s' % hdd_object.get_id())

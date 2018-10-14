"""Provides create VM parser."""

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


class CreateParser(object):
    """Handle VM create parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for creating VMs"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        self.create_parser = self.parent_subparser.add_parser(
            'create', help='Create VM',
            parents=[self.parent_parser])

        # Add arguments for creating a VM
        self.create_parser.add_argument('--memory', dest='memory', metavar='Memory',
                                        required=True, type=int,
                                        help='Amount of memory to allocate to the VM (MiB)')
        self.create_parser.add_argument('--disk-size', dest='disk_size', metavar='Disk Size',
                                        type=int, default=None,
                                        help='Size of disk to be created for the VM (MB)')
        self.create_parser.add_argument(
            '--cpu-count', dest='cpu_count', metavar='CPU Count',
            help='Number of virtual CPU cores to be allocated to the VM',
            type=int, required=True
        )
        self.create_parser.add_argument(
            '--network', dest='networks', metavar='Network Connection',
            type=str, action='append',
            help='Name of networks to connect VM to (each network has a separate NIC)'
        )
        self.create_parser.add_argument('--nodes', dest='nodes', action='append',
                                        help=('Specify the nodes that the VM will be'
                                              ' hosted on, if a Drbd storage-type'
                                              ' is specified'),
                                        default=None)

        self.create_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        # Determine if machine is configured to use DRBD
        # @TODO: Update to use List of storage options from Hard drive factory
        self.create_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type',
                                        type=str, default=None, choices=['Local', 'Drbd'])
        self.create_parser.add_argument('--storage-backend', dest='storage_backend',
                                        metavar='STorage Backend',
                                        type=str, default=None)
        # @TODO: Add choices for hard drive driver
        self.create_parser.add_argument('--hdd-driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)
        # @TODO: Add choices for graphics driver
        self.create_parser.add_argument('--graphics-driver', dest='graphics_driver',
                                        metavar='Graphics Driver', type=str,
                                        help='Driver for graphics', default=None)
        # @TODO: Add choices for modifciation flags
        self.create_parser.add_argument('--modification-flag', help='Add VM modification flag',
                                        dest='modification_flags', action='append')

    def handle_create(self, p_, args):
        """Handle create"""
        if args.storage_backend:
            storage_factory = p_.rpc.get_connection('storage_factory')
            storage_backend = storage_factory.get_object_by_name(args.storage_backend)
            p_.rpc.annotate_object(storage_backend)
        else:
            storage_backend = None
        storage_type = args.storage_type or None

        # Convert memory allocation from MiB to KiB
        memory_allocation = int(args.memory) * 1024
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        hard_disks = [args.disk_size] if args.disk_size is not None else []
        mod_flags = args.modification_flags or []
        vm_factory.create(
            name=args.vm_name,
            cpu_cores=args.cpu_count,
            memory_allocation=memory_allocation,
            hard_drives=hard_disks,
            network_interfaces=args.networks,
            storage_type=storage_type,
            hard_drive_driver=args.hard_disk_driver,
            graphics_driver=args.graphics_driver,
            available_nodes=args.nodes,
            modification_flags=mod_flags,
            storage_backend=storage_backend)

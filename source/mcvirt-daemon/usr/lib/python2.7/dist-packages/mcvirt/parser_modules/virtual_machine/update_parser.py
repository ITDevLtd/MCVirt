"""Provides VM update parser."""

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

from mcvirt.exceptions import ArgumentParserException


class UpdateParser(object):
    """Handle VM update parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for starting VMs."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for updating a VM
        self.update_parser = self.parent_subparser.add_parser(
            'update', help='Update VM Configuration',
            parents=[self.parent_parser])
        self.update_parser.set_defaults(func=self.handle_update)

        self.update_parser.add_argument('--memory', dest='memory', metavar='Memory', type=str,
                                        help=('Amount of memory to allocate to the VM'
                                              '(specify with suffix, e.g. 8GB)'))
        self.update_parser.add_argument(
            '--cpu-count', dest='cpu_count', metavar='CPU Count', type=int,
            help='Number of virtual CPU cores to be allocated to the VM'
        )
        self.update_parser.add_argument(
            '--add-network',
            dest='add_network',
            metavar='Add Network',
            type=str,
            help='Adds a NIC to the VM, connected to the given network'
        )
        self.update_parser.add_argument(
            '--remove-network',
            dest='remove_network',
            metavar='Remove Network',
            type=str,
            help='Removes a NIC from VM with the given MAC-address (e.g. \'00:00:00:00:00:00)\''
        )
        self.update_parser.add_argument(
            '--change-network',
            dest='change_network',
            metavar='MAC address of network interface',
            type=str,
            help=("Change the network for a NIC given the MAC-address (e.g. 00:00:00:00:00:00)\n" +
                  "To be used with --new-network")
        )
        self.update_parser.add_argument(
            '--new-network',
            dest='new_network',
            metavar='New Network',
            type=str,
            help=("Specify the network for the NIC\n" +
                  "To be used with --change-network")
        )
        self.update_parser.add_argument('--add-disk', dest='add_disk', metavar='Add Disk',
                                        type=str, help=('Add disk to the VM '
                                                        '(specify with suffix, e.g. 8GB)'))
        self.update_parser.add_argument('--delete-disk', dest='delete_disk', metavar='Disk ID',
                                        type=int, help='Remove a hard drive from a VM')
        self.update_parser.add_argument('--storage-type', dest='storage_type',
                                        metavar='Storage backing type', type=str,
                                        default=None, choices=['Local', 'Drbd'])
        self.update_parser.add_argument('--hdd-driver', metavar='Hard Drive Driver',
                                        dest='hard_disk_driver', type=str,
                                        help='Driver for hard disk',
                                        default=None)
        self.update_parser.add_argument('--graphics-driver', metavar='Graphics Driver',
                                        dest='graphics_driver', type=str,
                                        help='Driver for graphics',
                                        default=None)
        self.update_parser.add_argument('--increase-disk', dest='increase_disk',
                                        metavar='Increase Disk', type=str,
                                        help=('Increases VM disk by provided amount'
                                              '(specify with suffix, e.g. 8GB)'))
        self.update_parser.add_argument('--disk-id', dest='disk_id', metavar='Disk Id', type=int,
                                        help='The ID of the disk to be increased/removed')
        self.update_parser.add_argument('--attach-iso', '--iso', dest='iso', metavar='ISO Name',
                                        type=str, default=None, nargs='?',
                                        help=('Attach an ISO to a running VM.'
                                              ' Specify without value to detach ISO.'))
        self.update_parser.add_argument('--attach-usb-device', dest='attach_usb_device',
                                        metavar='bus,device', help=('Specify bus/device for USB '
                                                                    'device to connect, e.g. 5,2'),
                                        type=str, default=None)
        self.update_parser.add_argument('--detach-usb-device', dest='detach_usb_device',
                                        metavar='bus,device', help=('Specify bus/device for USB '
                                                                    'device to detach, e.g. 5,2'),
                                        type=str, default=None)
        self.vm_autostart_mutual_group = self.update_parser.add_mutually_exclusive_group(
            required=False
        )
        self.vm_autostart_mutual_group.add_argument('--autostart-on-boot', action='store_true',
                                                    dest='autostart_boot',
                                                    help=('Update VM to automatically '
                                                          'start on boot'))
        self.vm_autostart_mutual_group.add_argument('--autostart-on-poll', action='store_true',
                                                    dest='autostart_poll',
                                                    help=('Update VM to automatically start on '
                                                          'autostart watchdog poll'))
        self.vm_autostart_mutual_group.add_argument('--autostart-disable', action='store_true',
                                                    dest='autostart_disable',
                                                    help='Disable autostart of VM')
        self.update_parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')
        self.update_parser.add_argument('--add-flag', help='Add VM modification flag',
                                        dest='add_flags', action='append')
        self.update_parser.add_argument('--remove-flag', help='Remove VM modification flag',
                                        dest='remove_flags', action='append')

        self.delete_protection_mutual_group = self.update_parser.add_mutually_exclusive_group(
            required=False)
        self.delete_protection_mutual_group.add_argument(
            '--enable-delete-protection', dest='enable_delete_protection',
            action='store_true',
            help='Enable VM delete protection.')
        self.delete_protection_mutual_group.add_argument(
            '--disable-delete-protection', type=str,
            dest='disable_delete_protection',
            help='Disable VM delete protection. Must provide name of VM in reverse.')

        self.memballoon_mutual_group = self.update_parser.add_mutually_exclusive_group(
            required=False)
        self.memballoon_mutual_group.add_argument(
            '--enable-memballoon', dest='enable_memballoon',
            action='store_true',
            help='Enable VM memory ballooning.')
        self.memballoon_mutual_group.add_argument(
            '--disable-memballoon', dest='disable_memballoon',
            action='store_true',
            help='Disable VM memory ballooning.')

        self.memballoon_deflation_mutual_group = self.update_parser.add_mutually_exclusive_group(
            required=False)
        self.memballoon_deflation_mutual_group.add_argument(
            '--enable-memballoon-deflation', dest='enable_memballoon_deflation',
            action='store_true',
            help='Enable VM memory balloon deflation.')
        self.memballoon_deflation_mutual_group.add_argument(
            '--disable-memballoon-deflation', dest='disable_memballoon_deflation',
            action='store_true',
            help='Disable VM memory balloon deflation.')

    def handle_update(self, p_, args):
        """Handle VM update."""
        if bool(args.change_network) != bool(args.new_network):
            raise ArgumentParserException('--new-network must be used with --change-network')
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)

        if args.memory:
            vm_object.update_ram(args.memory)
            p_.print_status(
                'RAM allocation will be changed to %s on next VM boot.' % args.memory
            )

        if args.cpu_count:
            old_cpu_count = vm_object.get_cpu()
            vm_object.update_cpu(args.cpu_count, old_value=old_cpu_count)
            p_.print_status(
                'Number of virtual cores will be changed from %s to %s.' %
                (old_cpu_count, args.cpu_count)
            )

        if args.remove_network:
            network_adapter_factory = p_.rpc.get_connection('network_adapter_factory')
            network_adapter_object = network_adapter_factory.getNetworkAdapterByMacAdress(
                vm_object, args.remove_network
            )
            p_.rpc.annotate_object(network_adapter_object)
            network_adapter_object.delete()

        if args.add_network:
            network_factory = p_.rpc.get_connection('network_factory')
            network_adapter_factory = p_.rpc.get_connection('network_adapter_factory')
            network_object = network_factory.get_network_by_name(args.add_network)
            p_.rpc.annotate_object(network_object)
            network_adapter_factory.create(vm_object, network_object)

        if args.change_network:
            network_adapter_factory = p_.rpc.get_connection('network_adapter_factory')
            network_adapter_object = network_adapter_factory.getNetworkAdapterByMacAdress(
                vm_object, args.change_network
            )
            p_.rpc.annotate_object(network_adapter_object)
            network_factory = p_.rpc.get_connection('network_factory')
            network_object = network_factory.get_network_by_name(args.new_network)
            p_.rpc.annotate_object(network_object)
            network_adapter_object.change_network(network_object)

        if args.add_disk:
            hard_drive_factory = p_.rpc.get_connection('hard_drive_factory')
            hard_drive_factory.create(size=args.add_disk,
                                      storage_type=args.storage_type,
                                      driver=args.hard_disk_driver,
                                      vm_object=vm_object)
        if args.delete_disk:
            hard_drive_attachment_factory = p_.rpc.get_connection('hard_drive_attachment_factory')
            hard_drive_object = hard_drive_attachment_factory.get_object(
                vm_object, args.delete_disk).get_hard_drive_object()
            p_.rpc.annotate_object(hard_drive_object)
            hard_drive_object.delete()

        if args.increase_disk and args.disk_id:
            hard_drive_attachment_factory = p_.rpc.get_connection('hard_drive_attachment_factory')
            hard_drive_object = hard_drive_attachment_factory.get_object(
                vm_object, args.disk_id).get_hard_drive_object()
            p_.rpc.annotate_object(hard_drive_object)
            hard_drive_object.increase_size(args.increase_disk)

        if args.iso or args.iso is None:
            vm_object.update_iso(args.iso)

        if args.graphics_driver:
            vm_object.update_graphics_driver(args.graphics_driver)

        if args.autostart_boot:
            vm_object.set_autostart_state('ON_BOOT')
        elif args.autostart_poll:
            vm_object.set_autostart_state('ON_POLL')
        else:
            vm_object.set_autostart_state('NO_AUTOSTART')

        if args.attach_usb_device:
            usb_device = vm_object.get_usb_device(*args.attach_usb_device.split(','))
            p_.rpc.annotate_object(usb_device)
            usb_device.attach()
        if args.detach_usb_device:
            usb_device = vm_object.get_usb_device(*args.detach_usb_device.split(','))
            p_.rpc.annotate_object(usb_device)
            usb_device.detach()

        if args.add_flags or args.remove_flags:
            add_flags = args.add_flags or []
            remove_flags = args.remove_flags or []
            vm_object.update_modification_flags(add_flags=add_flags, remove_flags=remove_flags)
            flags_str = ", ".join(vm_object.get_modification_flags())
            p_.print_status('Modification flags set to: %s' % (flags_str or 'None'))

        if args.enable_delete_protection:
            vm_object.enable_delete_protection()

        if args.disable_delete_protection:
            vm_object.disable_delete_protection(args.disable_delete_protection)

        if args.enable_memballoon or args.disable_memballoon:
            vm_object.set_memballoon_state(args.enable_memballoon)

        if args.enable_memballoon_deflation or args.disable_memballoon_deflation:
            vm_object.set_memballoon_deflation_state(args.enable_memballoon_deflation)
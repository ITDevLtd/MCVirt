"""Provides verifcation argument parser."""

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

from mcvirt.exceptions import DrbdVolumeNotInSyncException


class VerifyParser(object):
    """Handle verify parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for verifcation"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for VM verification
        self.parser = self.parent_subparser.add_parser(
            'verify',
            help='Perform verification of VMs',
            parents=[
                self.parent_parser])
        self.parser.set_defaults(func=self.handle_verify)
        self.verify_mutual_exclusive_group = self.parser.add_mutually_exclusive_group(
            required=True
        )
        self.verify_mutual_exclusive_group.add_argument('--all', dest='all', action='store_true',
                                                        help='Verifies all of the VMs')
        self.verify_mutual_exclusive_group.add_argument('vm_name', metavar='VM Name', nargs='?',
                                                        help='Specify a single VM to verify')

    def handle_verify(self, p_, args):
        """Hanlde verify"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        if args.vm_name:
            vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
            # @TODO remove this line
            p_.rpc.annotate_object(vm_object)
            vm_objects = [vm_object]
        elif args.all:
            vm_objects = vm_factory.get_all_virtual_machines()

        # Iterate over the VMs and check each disk
        failures = []
        for vm_object in vm_objects:
            p_.rpc.annotate_object(vm_object)
            for disk_object in vm_object.get_hard_drive_objects():
                p_.rpc.annotate_object(disk_object)
                if disk_object.get_type() == 'Drbd':
                    # Catch any exceptions due to the Drbd volume not being in-sync
                    try:
                        disk_object.verify()
                        p_.print_status(
                            ('Drbd verification for %s completed '
                             'without out-of-sync blocks') %
                            vm_object.get_name()
                        )
                    except DrbdVolumeNotInSyncException, exc:
                        # Append the not-in-sync exception message to an array,
                        # so the rest of the disks can continue to be checked
                        failures.append(exc.message)

        # If there were any failures during the verification, raise the exception and print
        # all exception messages
        if failures:
            raise DrbdVolumeNotInSyncException("\n".join(failures))

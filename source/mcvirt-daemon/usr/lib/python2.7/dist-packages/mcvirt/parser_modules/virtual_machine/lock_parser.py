"""Provides lock argument parser."""

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

from mcvirt.constants import LockStates


class LockParser(object):
    """Handle lock parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for disk lock"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create sub-parser for managing VM locks
        self.parser = self.parent_subparser.add_parser(
            'lock', help='Perform verification of VMs',
            parents=[self.parent_parser])
        self.parser.set_defaults(func=self.handle_lock)
        self.lock_mutual_exclusive_group = self.parser.add_mutually_exclusive_group(
            required=True
        )
        self.lock_mutual_exclusive_group.add_argument('--check-lock', dest='check_lock',
                                                      help='Checks the lock status of a VM',
                                                      action='store_true')
        self.lock_mutual_exclusive_group.add_argument('--lock', dest='lock', help='Locks a VM',
                                                      action='store_true')
        self.lock_mutual_exclusive_group.add_argument('--unlock', dest='unlock',
                                                      help='Unlocks a VM', action='store_true')
        self.parser.add_argument('vm_name', metavar='VM Name', type=str, help='Name of VM')

    def handle_lock(self, p_, args):
        """Handle lock"""
        vm_factory = p_.rpc.get_connection('virtual_machine_factory')
        vm_object = vm_factory.get_virtual_machine_by_name(args.vm_name)
        p_.rpc.annotate_object(vm_object)
        if args.lock:
            vm_object.setLockState(LockStates.LOCKED.value)
        if args.unlock:
            vm_object.setLockState(LockStates.UNLOCKED.value)
        if args.check_lock:
            p_.print_status(LockStates(vm_object.getLockState()).name)

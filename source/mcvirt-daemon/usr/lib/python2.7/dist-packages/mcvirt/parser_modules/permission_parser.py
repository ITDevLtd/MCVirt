"""Provides permission parser."""

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


class PermissionParser(object):
    """Handle permission parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for managing permissions VMs"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Get arguments for making permission changes
        self.permission_parser = self.parent_subparser.add_parser(
            'permission',
            help='Update user permissions',
            parents=[self.parent_parser]
        )
        self.permission_parser.set_defaults(func=self.handle_permission)

        self.permission_parser.add_argument(
            '--add-user',
            dest='add_user',
            metavar='Add user to user group',
            type=str,
            help=('DEPRECATED (will be removed in v10.0.0): '
                  'Adds a given user to a VM, allowing them to perform basic functions.')
        )
        self.permission_parser.add_argument(
            '--delete-user',
            dest='delete_user',
            metavar='Remove user from user group',
            type=str,
            help=('DEPRECATED (will be removed in v10.0.0): '
                  'Removes a given user from a VM. This prevents '
                  'them to perform basic functions.')
        )
        self.permission_parser.add_argument(
            '--add-owner',
            dest='add_owner',
            metavar='Add user to owner group',
            type=str,
            help=('DEPRECATED (will be removed in v10.0.0): '
                  'Adds a given user as an owner to a VM, '
                  'allowing them to perform basic functions and manager users.')
        )
        self.permission_parser.add_argument(
            '--delete-owner',
            dest='delete_owner',
            metavar='Remove user from owner group',
            type=str,
            help=('DEPRECATED (will be removed in v10.0.0): '
                  'Removes a given owner from a VM. '
                  'This prevents them to perform basic functions and manager users.')
        )
        self.permission_parser.add_argument(
            '--add-superuser',
            dest='add_superuser',
            metavar='Add user to superuser group',
            type=str,
            help=('Adds a given user to the global superuser role. '
                  'This allows the user to completely manage the MCVirt node/cluster')
        )
        self.permission_parser.add_argument(
            '--delete-superuser',
            dest='delete_superuser',
            metavar='Removes user from the superuser group',
            type=str,
            help='Removes a given user from the superuser group'
        )
        self.permission_target_group = self.permission_parser.add_mutually_exclusive_group(
            required=True
        )
        self.permission_target_group.add_argument('vm_name', metavar='VM Name',
                                                  type=str, help='Name of VM', nargs='?')
        self.permission_target_group.add_argument('--global', dest='global', action='store_true',
                                                  help='Set a global MCVirt permission')

        self.permission_target_group.add_argument(
            '--list',
            dest='list',
            action='store_true',
            help='List available permissions'
        )

    def handle_permission(self, p_, args):
        """Handle permission changes"""
        auth_object = p_.rpc.get_connection('auth')
        p_.rpc.annotate_object(auth_object)

        if args.list:
            p_.print_status(auth_object.list_permissions())
            return

        if (args.add_superuser or args.delete_superuser) and args.vm_name:
            raise ArgumentParserException('Superuser groups are global-only roles')

        if args.vm_name:
            vm_factory = p_.rpc.get_connection('virtual_machine_factory')
            vm_object = vm_factory.getVirtualMachineByName(args.vm_name)
            p_.rpc.annotate_object(vm_object)
            permission_destination_string = 'role on VM %s' % vm_object.get_name()
        else:
            vm_object = None
            permission_destination_string = 'global role'

        user_factory = p_.rpc.get_connection('user_factory')
        p_.rpc.annotate_object(user_factory)

        if args.add_user:
            user_object = user_factory.get_user_by_username(args.add_user)
            p_.rpc.annotate_object(user_object)
            group_factory = p_.rpc.get_connection('group_factory')
            group = group_factory.get_object_by_name('user')
            p_.rpc.annotate_object(group)
            group.add_user(
                user=user_object,
                virtual_machine=vm_object)
            p_.print_status(
                'Successfully added \'%s\' to \'user\' %s' %
                (args.add_user, permission_destination_string))

        if args.delete_user:
            user_object = user_factory.get_user_by_username(args.delete_user)
            p_.rpc.annotate_object(user_object)
            group_factory = p_.rpc.get_connection('group_factory')
            group = group_factory.get_object_by_name('user')
            p_.rpc.annotate_object(group)
            group.remove_user(
                user=user_object,
                virtual_machine=vm_object)
            p_.print_status(
                'Successfully removed \'%s\' from \'user\' %s' %
                (args.delete_user, permission_destination_string))

        if args.add_owner:
            user_object = user_factory.get_user_by_username(args.add_owner)
            p_.rpc.annotate_object(user_object)
            group_factory = p_.rpc.get_connection('group_factory')
            group = group_factory.get_object_by_name('owner')
            p_.rpc.annotate_object(group)
            group.add_user(
                user=user_object,
                virtual_machine=vm_object)
            p_.print_status(
                'Successfully added \'%s\' to \'owner\' %s' %
                (args.add_owner, permission_destination_string))

        if args.delete_owner:
            user_object = user_factory.get_user_by_username(args.delete_owner)
            p_.rpc.annotate_object(user_object)
            group_factory = p_.rpc.get_connection('group_factory')
            group = group_factory.get_object_by_name('owner')
            p_.rpc.annotate_object(group)
            group.remove_user(
                user=user_object,
                virtual_machine=vm_object)
            p_.print_status(
                'Successfully removed \'%s\' from \'owner\' %s' %
                (args.delete_owner, permission_destination_string))

        if args.add_superuser:
            user_object = user_factory.get_user_by_username(args.add_superuser)
            p_.rpc.annotate_object(user_object)
            auth_object.add_superuser(user_object=user_object)
            p_.print_status('Successfully added %s to the global superuser group' %
                            args.add_superuser)
        if args.delete_superuser:
            user_object = user_factory.get_user_by_username(args.delete_superuser)
            p_.rpc.annotate_object(user_object)
            auth_object.delete_superuser(user_object=user_object)
            p_.print_status('Successfully removed %s from the global superuser group ' %
                            args.delete_superuser)

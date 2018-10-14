"""Provides Group argument parser."""

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


class GroupParser(object):
    """Handle group parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for group management"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        self.parser = self.parent_subparser.add_parser(
            'group',
            help='Manage user groups',
            parents=[self.parent_parser]
        )

        self.sub_parsers = self.parser.add_subparsers(
            dest='group_action', metavar='Group Action',
            help='Action to perform'
        )

        self.register_list()
        self.register_create()
        self.register_delete()
        self.register_add_permission()
        self.register_remove_permission()
        self.register_add_user()
        self.register_remove_user()

    def register_list(self):
        """Register parser for listing group"""
        self.create_parser = self.sub_parsers.add_parser(
            'list',
            help='List the groups',
            parents=[self.parent_parser])
        self.create_parser.set_defaults(func=self.handle_list)

    def handle_list(self, args, rpc, print_status):
        """Perform list of groups"""
        group_factory = rpc.get_connection('group_factory')
        print_status(group_factory.list())

    def register_create(self):
        """Register parser for creating group"""
        self.create_parser = self.sub_parsers.add_parser(
            'create',
            help='Create a permission group',
            parents=[self.parent_parser])
        self.create_parser.set_defaults(func=self.handle_create)
        self.create_parser.add_argument(dest='name', metavar='Group Name')

    def handle_create(self, args, rpc, print_status):
        """Perform creation of group"""
        group_factory = rpc.get_connection('group_factory')
        group_factory.create(args.name)
        print_status('Created group \'%s\'' % args.name)

    def register_delete(self):
        """Register parser for deleting group"""
        self.delete_parser = self.sub_parsers.add_parser(
            'delete',
            help='Delete a permission group',
            parents=[self.parent_parser])
        self.delete_parser.set_defaults(func=self.handle_delete)
        self.delete_parser.add_argument(dest='name', metavar='Group Name')

    def handle_delete(self, args, rpc, print_status):
        """Perform deletionn of group"""
        group_factory = rpc.get_connection('group_factory')
        group = group_factory.get_object_by_name(args.name)
        rpc.annotate_object(group)
        group.delete()
        print_status('Deleted group \'%s\'' % args.name)

    def register_add_permission(self):
        """Register parser for adding permission to group"""
        self.add_user_parser = self.sub_parsers.add_parser(
            'add-permission',
            help='Add a permission to a group',
            parents=[self.parent_parser])
        self.add_user_parser.set_defaults(func=self.handle_add_permission)
        self.add_user_parser.add_argument(dest='name', metavar='Group Name')
        self.add_user_parser.add_argument(dest='permissions', nargs='+', metavar='Usernames',
                                          help=('List of permissions to add to group '
                                                '(see mcvirt permission --list)'))

    def handle_add_permission(self, args, rpc, print_status):
        """Perform addition of permission to group"""
        group_factory = rpc.get_connection('group_factory')
        group = group_factory.get_object_by_name(args.name)
        rpc.annotate_object(group)

        for permission in args.permissions:
            permission = permission.upper()
            group.add_permission(permission)
            print_status('Added \'%s\' to group \'%s\'' % (permission, args.name))

    def register_remove_permission(self):
        """Register parser for removing permission from group"""
        self.remove_user_parser = self.sub_parsers.add_parser(
            'remove-permission',
            help='Remove a permission from a group',
            parents=[self.parent_parser])
        self.remove_user_parser.set_defaults(func=self.handle_remove_permission)
        self.remove_user_parser.add_argument(dest='name', metavar='Group Name')
        self.remove_user_parser.add_argument(dest='permissions', nargs='+', metavar='Permissions',
                                             help=('List of permissions to remove from group '
                                                   '(see mcvirt permission --list)'))

    def handle_remove_permission(self, args, rpc, print_status):
        """Perform removal of permission from group"""
        group_factory = rpc.get_connection('group_factory')
        group = group_factory.get_object_by_name(args.name)
        rpc.annotate_object(group)

        for permission in args.permissions:
            permission = permission.upper()
            group.remove_permission(permission)
            print_status('Removed \'%s\' to group \'%s\'' % (permission, args.name))

    def register_add_user(self):
        """Register parser for adding user to group"""
        self.add_user_parser = self.sub_parsers.add_parser(
            'add-user',
            help='Add a user to a permission group',
            parents=[self.parent_parser])
        self.add_user_parser.set_defaults(func=self.handle_add_user)
        self.add_user_parser.add_argument(dest='name', metavar='Group Name')
        self.add_user_parser.add_argument('--virtual-machine', metavar='Virtual Machine Name',
                                          dest='virtual_machine', required=False,
                                          help=('Optional virtual machine to limit '
                                                'the group access to.'))
        self.add_user_parser.add_argument(dest='usernames', nargs='+', metavar='Usernames',
                                          help='List of users to add to group')

    def handle_add_user(self, args, rpc, print_status):
        """Perform adding of user to group"""
        group_factory = rpc.get_connection('group_factory')
        group = group_factory.get_object_by_name(args.name)
        rpc.annotate_object(group)
        user_factory = rpc.get_connection('user_factory')

        if args.virtual_machine:
            virtual_machine_factory = rpc.get_connection('virtual_machine_factory')
            virtual_machine = virtual_machine_factory.getVirtualMachineByName(args.virtual_machine)
            rpc.annotate_object(virtual_machine)
        else:
            virtual_machine = None

        for username in args.usernames:
            user = user_factory.get_user_by_username(username)
            rpc.annotate_object(user)
            group.add_user(user=user, virtual_machine=virtual_machine)
            print_status('Added \'%s\' to group \'%s\'' % (username, args.name))

    def register_remove_user(self):
        """Register parser for removing user from group"""
        self.remove_user_parser = self.sub_parsers.add_parser(
            'remove-user',
            help='Remove a user from a permission group',
            parents=[self.parent_parser])
        self.remove_user_parser.set_defaults(func=self.handle_remove_user)
        self.remove_user_parser.add_argument(dest='name', metavar='Group Name')
        self.remove_user_parser.add_argument('--virtual-machine', metavar='Virtual Machine Name',
                                             dest='virtual_machine', required=False,
                                             help=('Optional virtual machine that the group '
                                                   'access was restricted to.'))
        self.remove_user_parser.add_argument(dest='usernames', nargs='+', metavar='Usernames',
                                             help='List of users to remove from group')

    def handle_remove_user(self, args, rpc, print_status):
        """Perform removal of user from group"""
        group_factory = rpc.get_connection('group_factory')
        group = group_factory.get_object_by_name(args.name)
        rpc.annotate_object(group)
        user_factory = rpc.get_connection('user_factory')

        if args.virtual_machine:
            virtual_machine_factory = rpc.get_connection('virtual_machine_factory')
            virtual_machine = virtual_machine_factory.getVirtualMachineByName(args.virtual_machine)
            rpc.annotate_object(virtual_machine)
        else:
            virtual_machine = None

        for username in args.usernames:
            user = user_factory.get_user_by_username(username)
            rpc.annotate_object(user)
            group.remove_user(user=user, virtual_machine=virtual_machine)
            print_status('Removed \'%s\' to group \'%s\'' % (username, args.name))

"""Provides User argument parser."""

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

from mcvirt.system import System


class UserParser(object):
    """Handle user parser."""

    def __init__(self, subparser, parent_parser):
        """Create subparser for user management."""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        self.parser = self.parent_subparser.add_parser(
            'user',
            help='User managment',
            parents=[self.parent_parser]
        )

        self.sub_parsers = self.parser.add_subparsers(
            dest='user_action',
            help='User managment action to perform',
            metavar='Action'
        )

        self.register_list()
        self.register_change_password()
        self.register_create()
        self.register_delete()
        self.register_add_permission()
        self.register_remove_permission()

    def register_list(self):
        """Register parser for listing group."""
        self.list_parser = self.sub_parsers.add_parser(
            'list',
            help='List users',
            parents=[self.parent_parser])
        self.list_parser.set_defaults(func=self.handle_list)

    def handle_list(self, p_, args):
        """Perform list of groups."""
        user_factory = p_.rpc.get_connection('user_factory')
        p_.print_status(user_factory.list())

    def register_change_password(self):
        """Register change password parser."""
        self.change_password_parser = self.sub_parsers.add_parser(
            'change-password',
            help='Change a user password',
            parents=[self.parent_parser]
        )
        self.change_password_parser.set_defaults(func=self.handle_change_password)
        self.change_password_parser.add_argument(
            '--new-password',
            dest='new_password',
            metavar='New password',
            help='The new password'
        )
        self.change_password_parser.add_argument(
            '--target-user',
            dest='target_user',
            metavar='Target user',
            help='The user to change the password of'
        )

    def handle_change_password(self, p_, args):
        """Handle change password."""
        user_factory = p_.rpc.get_connection('user_factory')
        target_user = args.target_user or p_.username
        user = user_factory.get_user_by_username(target_user)
        p_.rpc.annotate_object(user)
        new_password = args.new_password or System.getNewPassword()
        user.set_password(new_password)
        p_.print_status('Updated password')

    def register_create(self):
        """Register create parser."""
        self.create_parser = self.sub_parsers.add_parser(
            'create',
            help='Create a new user',
            parents=[self.parent_parser]
        )
        self.create_parser.set_defaults(func=self.handle_create)
        self.create_parser.add_argument(
            'new_username',
            metavar='User',
            type=str,
            help='The new user to create'
        )
        self.create_user_mut_ex_group = self.create_parser.add_mutually_exclusive_group(
            required=False
        )
        self.create_user_mut_ex_group.add_argument(
            '--user-password',
            dest='new_user_password',
            metavar='New password',
            help='The password for the new user'
        )
        self.create_user_mut_ex_group.add_argument(
            '--generate-password',
            dest='generate_password',
            action='store_true',
            help='Generate a password for the new user'
        )

    def handle_create(self, p_, args):
        """Handle creation."""
        user_factory = p_.rpc.get_connection('user_factory')

        if args.generate_password:
            new_password = user_factory.generate_password()
        else:
            new_password = args.new_user_password or System.getNewPassword()

        user_factory.create(args.new_username, new_password)

        p_.print_status('New user details:\nUsername: %s' % args.new_username)
        if args.generate_password:
            p_.print_status('Password: %s' % new_password)

    def register_delete(self):
        """Register deletion parser."""
        self.delete_parser = self.sub_parsers.add_parser(
            'delete',
            help='Delete a user',
            parents=[self.parent_parser]
        )
        self.delete_parser.set_defaults(func=self.handle_delete)
        self.delete_parser.add_argument(
            'delete_username',
            metavar='User',
            type=str,
            help='The user to delete'
        )

    def handle_delete(self, p_, args):
        """Handle deletion."""
        user_factory = p_.rpc.get_connection('user_factory')
        user = user_factory.get_user_by_username(args.delete_username)
        p_.rpc.annotate_object(user)
        user.delete()
        p_.print_status('Deleted user')

    def register_add_permission(self):
        """Register parser for adding permission to user."""
        self.add_permission_parser = self.sub_parsers.add_parser(
            'add-permission',
            help='Add a permission to a user',
            parents=[self.parent_parser])
        self.add_permission_parser.set_defaults(func=self.handle_add_permission)
        self.add_permission_parser.add_argument(dest='user', metavar='Username')
        self.add_permission_parser.add_argument(dest='permissions', nargs='+',
                                                metavar='Permissions',
                                                help=('List of permissions to add to user '
                                                      '(see mcvirt permission --list)'))

    def handle_add_permission(self, p_, args):
        """Perform addition of permission to user."""
        user_factory = p_.rpc.get_connection('user_factory')
        user = user_factory.get_user_by_username(args.user)
        p_.rpc.annotate_object(user)

        for permission in args.permissions:
            permission = permission.upper()
            user.add_permission(permission)
            p_.print_status('Added \'%s\' to user \'%s\'' % (permission, args.user))

    def register_remove_permission(self):
        """Register parser for removing permission from user."""
        self.remove_permission_parser = self.sub_parsers.add_parser(
            'remove-permission',
            help='Remove a permission from a user',
            parents=[self.parent_parser])
        self.remove_permission_parser.set_defaults(func=self.handle_remove_permission)
        self.remove_permission_parser.add_argument(dest='user', metavar='Username')
        self.remove_permission_parser.add_argument(dest='permissions', nargs='+',
                                                   metavar='Permissions',
                                                   help=('List of permissions to remove '
                                                         'from user (see mcvirt '
                                                         'permission --list)'))

    def handle_remove_permission(self, p_, args):
        """Perform removal of permission from user."""
        user_factory = p_.rpc.get_connection('user_factory')
        user = user_factory.get_user_by_username(args.user)
        p_.rpc.annotate_object(user)

        for permission in args.permissions:
            permission = permission.upper()
            user.remove_permission(permission)
            p_.print_status('Removed \'%s\' to user \'%s\'' % (permission, args.user))

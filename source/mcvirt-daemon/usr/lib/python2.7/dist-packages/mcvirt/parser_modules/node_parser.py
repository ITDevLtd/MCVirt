"""Provides node argument parser."""

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

import os


class NodeParser(object):
    """Handle node parser"""

    def __init__(self, subparser, parent_parser):
        """Create subparser for node related config"""
        self.parent_subparser = subparser
        self.parent_parser = parent_parser

        # Create subparser for commands relating to the local node configuration
        self.parser = self.parent_subparser.add_parser(
            'node',
            help='Modify configurations relating to the local node',
            parents=[self.parent_parser]
        )
        self.parser.set_defaults(func=self.handle_node)

        self.node_watchdog_parser = self.parser.add_argument_group(
            'Watchdog', 'Update configurations for watchdogs'
        )
        self.node_watchdog_parser.add_argument('--set-autostart-interval',
                                               dest='autostart_interval',
                                               metavar='Autostart Time (Seconds)',
                                               help=('Set the interval period (seconds) for '
                                                     'the autostart watchdog. '
                                                     'Setting to \'0\' will disable the '
                                                     'watchdog polling.'),
                                               type=int)
        self.node_watchdog_parser.add_argument('--get-autostart-interval',
                                               dest='get_autostart_interval',
                                               action='store_true',
                                               help='Return the current autostart interval.')

        self.node_cluster_config = self.parser.add_argument_group(
            'Cluster', 'Configure the node-specific cluster configurations'
        )
        self.node_cluster_config.add_argument('--set-ip-address', dest='ip_address',
                                              metavar='Cluster IP Address',
                                              help=('Sets the cluster IP address'
                                                    ' for the local node,'
                                                    ' used for Drbd and cluster management.'))

        self.ldap_parser = self.parser.add_argument_group(
            'Ldap', 'Configure the LDAP authentication backend'
        )
        self.ldap_enable_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_enable_mutual_group.add_argument('--enable-ldap', dest='ldap_enable',
                                                   action='store_true', default=None,
                                                   help='Enable the LDAP authentication backend')
        self.ldap_enable_mutual_group.add_argument('--disable-ldap', dest='ldap_disable',
                                                   action='store_true',
                                                   help='Disable the LDAP authentication backend')

        self.ldap_server_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_server_mutual_group.add_argument('--server-uri', dest='ldap_server_uri',
                                                   metavar='LDAP Server URI', default=None,
                                                   help=('Specify the LDAP server URI.'
                                                         ' E.g. ldap://10.200.1.1:389'
                                                         ' ldaps://10.200.1.1'))
        self.ldap_server_mutual_group.add_argument('--clear-server-uri',
                                                   action='store_true',
                                                   dest='ldap_server_uri_clear',
                                                   help='Clear the server URI configuration.')
        self.ldap_base_dn_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_base_dn_mutual_group.add_argument('--base-dn', dest='ldap_base_dn',
                                                    metavar='LDAP Base DN', default=None,
                                                    help=('Base search DN for users. E.g. '
                                                          'ou=People,dc=my,dc=company,dc=com'))
        self.ldap_base_dn_mutual_group.add_argument('--clear-base-dn',
                                                    action='store_true',
                                                    dest='ldap_base_dn_clear',
                                                    help='Clear the base DN configuration.')
        self.ldap_bind_dn_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_bind_dn_mutual_group.add_argument('--bind-dn', dest='ldap_bind_dn',
                                                    metavar='LDAP Bind DN', default=None,
                                                    help=('DN for user to bind to LDAP. E.g. '
                                                          'cn=Admin,ou=People,dc=my,dc=company,'
                                                          'dc=com'))
        self.ldap_bind_dn_mutual_group.add_argument('--clear-bind-dn',
                                                    action='store_true',
                                                    dest='ldap_bind_dn_clear',
                                                    help='Clear the bind DN configuration.')
        self.ldap_base_pw_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_base_pw_mutual_group.add_argument('--bind-pass', dest='ldap_bind_pass',
                                                    metavar='LDAP Bind Password', default=None,
                                                    help='Password for bind account')
        self.ldap_base_pw_mutual_group.add_argument('--clear-bind-pass',
                                                    action='store_true',
                                                    dest='ldap_bind_pass_clear',
                                                    help='Clear the bind pass configuration.')
        self.ldap_user_search_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_user_search_mutual_group.add_argument('--user-search', dest='ldap_user_search',
                                                        metavar='LDAP search', default=None,
                                                        help=('LDAP query for user objects. E.g.'
                                                              ' (objectClass=posixUser)'))
        self.ldap_user_search_mutual_group.add_argument('--clear-user-search',
                                                        action='store_true',
                                                        dest='ldap_user_search_clear',
                                                        help='Clear the user search configuration')
        self.ldap_username_attribute_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_username_attribute_mutual_group.add_argument('--username-attribute',
                                                               default=None,
                                                               dest='ldap_username_attribute',
                                                               metavar='LDAP Username Attribute',
                                                               help=('LDAP username attribute.'
                                                                     ' E.g. uid'))
        self.ldap_username_attribute_mutual_group.add_argument(
            '--clear-username-attribute',
            action='store_true',
            dest='ldap_username_attribute_clear',
            help='Clear the username attribute configuration'
        )
        self.ldap_ca_cert_mutual_group = self.ldap_parser.add_mutually_exclusive_group(
            required=False
        )
        self.ldap_ca_cert_mutual_group.add_argument('--ca-cert-file', dest='ldap_ca_cert',
                                                    metavar='Path to CA file', default=None,
                                                    help=('Path to CA cert file for LDAP over'
                                                          ' TLS.'))
        self.ldap_ca_cert_mutual_group.add_argument('--clear-ca-cert-file',
                                                    action='store_true',
                                                    dest='ldap_ca_cert_clear',
                                                    help='Clear the store LDAP CA cert file.')

    def handle_node(self, p_, args):
        """Handle node change"""
        node = p_.rpc.get_connection('node')
        ldap = p_.rpc.get_connection('ldap_factory')

        if args.ip_address:
            node.set_cluster_ip_address(args.ip_address)
            p_.print_status('Successfully set cluster IP address to %s' % args.ip_address)

        if args.autostart_interval or args.autostart_interval == 0:
            autostart_watchdog = p_.rpc.get_connection('autostart_watchdog')
            autostart_watchdog.set_autostart_interval(args.autostart_interval)
        elif args.get_autostart_interval:
            autostart_watchdog = p_.rpc.get_connection('autostart_watchdog')
            p_.print_status(autostart_watchdog.get_autostart_interval())

        if args.ldap_enable:
            ldap.set_enable(True)
        elif args.ldap_disable:
            ldap.set_enable(False)

        ldap_args = {}
        if args.ldap_server_uri is not None:
            ldap_args['server_uri'] = args.ldap_server_uri
        elif args.ldap_server_uri_clear:
            ldap_args['server_uri'] = None
        if args.ldap_base_dn is not None:
            ldap_args['base_dn'] = args.ldap_base_dn
        elif args.ldap_base_dn_clear:
            ldap_args['base_dn'] = None
        if args.ldap_bind_dn is not None:
            ldap_args['bind_dn'] = args.ldap_bind_dn
        elif args.ldap_bind_dn_clear:
            ldap_args['bind_dn'] = None
        if args.ldap_bind_pass is not None:
            ldap_args['bind_pass'] = args.ldap_bind_pass
        elif args.ldap_bind_pass_clear:
            ldap_args['bind_pass'] = None
        if args.ldap_user_search is not None:
            ldap_args['user_search'] = args.ldap_user_search
        elif args.ldap_user_search_clear:
            ldap_args['user_search'] = None
        if args.ldap_username_attribute is not None:
            ldap_args['username_attribute'] = args.ldap_username_attribute
        elif args.ldap_username_attribute_clear:
            ldap_args['username_attribute'] = None
        if args.ldap_ca_cert:
            if not os.path.exists(args.ldap_ca_cert):
                raise Exception('Specified LDAP CA cert file cannot be found.')
            with open(args.ldap_ca_cert, 'r') as ca_crt_fh:
                ldap_args['ca_cert'] = ca_crt_fh.read()
        elif args.ldap_ca_cert_clear:
            ldap_args['ca_cert'] = None

        if len(ldap_args):
            ldap.set_config(**ldap_args)

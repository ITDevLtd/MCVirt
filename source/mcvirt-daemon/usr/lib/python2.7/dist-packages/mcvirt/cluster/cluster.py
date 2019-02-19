"""Provide cluster classes."""

# Copyright (c) 2014 - I.T. Dev Ltd
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

import json
import base64
import socket
from texttable import Texttable

import Pyro4

from mcvirt.utils import get_hostname
from mcvirt.exceptions import (NodeAlreadyPresent, NodeDoesNotExistException,
                               RemoteObjectConflict, ClusterNotInitialisedException,
                               InvalidConnectionString, DrbdNotInstalledException,
                               CouldNotConnectToNodeException, InaccessibleNodeException,
                               MissingConfigurationException, NodeVersionMismatch,
                               MCVirtTypeError, InvalidStorageConfiguration)
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.config.virtual_machine import VirtualMachine as VirtualMachineConfig
from mcvirt.config.hard_drive import HardDrive as HardDriveConfig
from mcvirt.auth.user_types.connection_user import ConnectionUser
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.client.rpc import Connection
from mcvirt.cluster.remote import Node
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.syslogger import Syslogger


class Cluster(PyroObject):
    """Class to perform node management within the MCVirt cluster."""

    @Expose()
    def generate_connection_info(self):
        """Generate required information to connect to this node from a remote node."""
        # Ensure user has required permissions
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_CLUSTER
        )

        # Ensure that the IP address configurations has been made correctly
        self.check_ip_configuration()

        # Create connection user
        user_factory = self.po__get_registered_object('user_factory')
        connection_username, connection_password = user_factory.generate_user(ConnectionUser)
        ssl_object = self.po__get_registered_object(
            'certificate_generator_factory').get_cert_generator(get_hostname())
        return [get_hostname(), self.get_cluster_ip_address(),
                connection_username, connection_password,
                ssl_object.get_ca_contents()]

    @Expose()
    def get_connection_string(self):
        """Generate a string to connect to this node from a remote cluster."""
        # Only superusers can generate a connection string
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_CLUSTER
        )

        # Generate dict with connection information. Convert to JSON and base64 encode
        connection_info = self.generate_connection_info()
        connection_info_dict = {
            'hostname': connection_info[0],
            'ip_address': connection_info[1],
            'username': connection_info[2],
            'password': connection_info[3],
            'ca_cert': connection_info[4]
        }
        connection_info_json = json.dumps(connection_info_dict)
        return base64.b64encode(connection_info_json)

    @Expose()
    def print_info(self):
        """Print information about the nodes in the cluster."""
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Node', 'IP Address', 'Status', 'CPU Usage', 'Memory Usage'))
        # Add this node to the table
        table.add_row((
            get_hostname(),
            self.get_cluster_ip_address(),
            'Local',
            self.po__get_registered_object('host_statistics').get_cpu_usage_string(),
            self.po__get_registered_object('host_statistics').get_memory_usage_string()))

        # Add remote nodes
        for node in self.get_nodes(return_all=True):
            node_config = self.get_node_config(node)
            node_status = 'Unreachable'
            cpu = ''
            ram = ''
            try:
                node_obj = self.get_remote_node(node)
                if node_obj is not None:
                    remote_stats = node_obj.get_connection('host_statistics')
                    cpu = remote_stats.get_cpu_usage_string()
                    ram = remote_stats.get_memory_usage_string()
                    node_status = 'Connected'
            except CouldNotConnectToNodeException:
                pass
            table.add_row((node, node_config['ip_address'],
                           node_status, cpu, ram))
        return table.draw()

    def check_node_versions(self):
        """Ensure that all nodes in the cluster are connected
        and checks the node Status
        """
        def check_version(connection):
            """Check node config on remote node."""
            node = connection.get_connection('node')
            return node.get_version()
        node_versions = self.run_remote_command(check_version)
        local_version = self.po__get_registered_object('node').get_version()
        for node in node_versions:
            if node_versions[node] != local_version:
                raise NodeVersionMismatch('Node %s is running MCVirt %s. Local version: %s' %
                                          (node, node_versions[node], local_version))

    @Expose(locking=True)
    def add_node_configuration(self, node_name, ip_address,
                               connection_user, connection_password,
                               ca_key):
        """Add MCVirt node to configuration, generates a cluster user on the remote node
        and stores credentials against node in the MCVirt configuration.
        """
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)

        # Create CA file
        ssl_object = self.po__get_registered_object(
            'certificate_generator_factory').get_cert_generator(node_name)
        ssl_object.ca_pub_file = ca_key

        # Connect to node and obtain cluster user
        remote = Connection(username=connection_user, password=connection_password,
                            host=node_name)
        remote_user_factory = remote.get_connection('user_factory')
        connection_user = remote_user_factory.get_user_by_username(connection_user)
        remote.annotate_object(connection_user)
        username, password = connection_user.create_cluster_user(host=get_hostname())

        # Add node to configuration file
        def add_node_config(mcvirt_config):
            """Add node config to MCVirt config."""
            mcvirt_config['cluster']['nodes'][node_name] = {
                'ip_address': ip_address,
                'username': username,
                'password': password
            }
        MCVirtConfig().update_config(add_node_config)

    def check_ip_configuration(self):
        """Perform various checks to ensure that the
        IP configuration is such that is suitable to be part of a cluster
        """
        # Ensure that the cluster IP address has been defined
        cluster_ip = self.get_cluster_ip_address()
        if not cluster_ip:
            raise MissingConfigurationException('IP address has not yet been configured')

        # Ensure that the hostname of the local machine does not resolve
        # to 127.0.0.1
        if socket.gethostbyname(get_hostname()).startswith('127.'):
            raise MissingConfigurationException(('Node hostname %s resolves to the localhost.'
                                                 ' Instead it should resolve to the cluster'
                                                 ' IP address') % get_hostname())
        resolve_ip = socket.gethostbyname(get_hostname())
        if resolve_ip != cluster_ip:
            raise MissingConfigurationException(('The local hostname (%s) should resolve the'
                                                 ' cluster IP address (%s). Instead it resolves'
                                                 ' to \'%s\'. Please correct this issue before'
                                                 ' continuing.') %
                                                (get_hostname(), cluster_ip, resolve_ip))

    @Expose(locking=True)
    def add_node(self, node_connection_string, location_overrides=None):
        """Connect to a remote MCVirt machine, setup shared authentication
        and clusters the machines.
        """
        # Ensure the user has privileges to manage the cluster
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)

        # Ensure that the IP address configurations has been made correctly
        self.check_ip_configuration()

        try:
            config_json = base64.b64decode(node_connection_string)
            node_config = json.loads(config_json)
            assert 'username' in node_config and node_config['username']
            assert 'password' in node_config and node_config['password']
            assert 'ip_address' in node_config and node_config['ip_address']
            assert 'hostname' in node_config and node_config['hostname']
            assert 'ca_cert' in node_config and node_config['ca_cert']
        except (MCVirtTypeError, TypeError, ValueError, AssertionError):
            raise InvalidConnectionString('Connection string is invalid')

        Syslogger.logger().debug('Decoded connect string. Adding node %s' %
                                 node_config['hostname'])

        # Determine if node is already connected to cluster
        if self.check_node_exists(node_config['hostname']):
            raise NodeAlreadyPresent(
                'Node %s is already connected to the cluster' % node_config['hostname'])

        # Create CA public key for machine
        ssl_object = self.po__get_registered_object(
            'certificate_generator_factory'
        ).get_cert_generator(node_config['hostname'])
        ssl_object.ca_pub_file = node_config['ca_cert']

        # If location_overrides was not specified, default to empty dict
        location_overrides = {} if location_overrides is None else location_overrides

        # Check remote machine, to ensure it can be synced without any
        # conflicts
        remote = Connection(username=node_config['username'], password=node_config['password'],
                            host=node_config['hostname'])
        self.check_remote_machine(remote, location_overrides=location_overrides)
        remote = None
        original_cluster_nodes = self.get_nodes()

        # Add remote node
        self.add_node_configuration(node_name=node_config['hostname'],
                                    ip_address=node_config['ip_address'],
                                    connection_user=node_config['username'],
                                    connection_password=node_config['password'],
                                    ca_key=node_config['ca_cert'])

        # Obtain node connection to new node
        remote_node = self.get_remote_node(node_config['hostname'])

        # Generate local connection user for new remote node
        local_connection_info = self.generate_connection_info()

        # Add the local node to the new remote node
        remote_cluster_instance = remote_node.get_connection('cluster')
        remote_cluster_instance.add_node_configuration(
            node_name=local_connection_info[0], ip_address=local_connection_info[1],
            connection_user=local_connection_info[2],
            connection_password=local_connection_info[3],
            ca_key=local_connection_info[4]
        )

        new_node_cert_gen_factory = remote_node.get_connection('certificate_generator_factory')

        # Create client certificates for libvirt for the new node to connect to the
        # current cluster node
        new_node_cert_gen = new_node_cert_gen_factory.get_cert_generator(get_hostname())
        remote_node.annotate_object(new_node_cert_gen)

        # Generate CSR
        csr = new_node_cert_gen.generate_csr()

        # Sign CSR
        cert_gen_factory = self.po__get_registered_object('certificate_generator_factory')
        cert_gen = cert_gen_factory.get_cert_generator(node_config['hostname'],
                                                       remote=True)
        pub_key = cert_gen.sign_csr(csr)

        # Add public key to new node
        new_node_cert_gen.add_public_key(pub_key)

        # Create client certificate for libvirt for the current cluster node to connect
        # to the new node
        cert_gen = cert_gen_factory.get_cert_generator(node_config['hostname'])

        # Generate CSR
        csr = cert_gen.generate_csr()

        # Sign CSR
        new_node_cert_gen = new_node_cert_gen_factory.get_cert_generator(
            get_hostname(), remote=True)
        remote_node.annotate_object(new_node_cert_gen)
        pub_key = new_node_cert_gen.sign_csr(csr)

        # Add public key to local node
        cert_gen.add_public_key(pub_key)

        # Sync credentials to/from old nodes in the cluster
        for original_node in original_cluster_nodes:
            # Share connection information between cluster node and new node
            original_node_remote = self.get_remote_node(original_node)
            original_cluster = original_node_remote.get_connection('cluster')
            original_node_con_info = original_cluster.generate_connection_info()
            remote_cluster_instance.add_node_configuration(
                node_name=original_node_con_info[0],
                ip_address=original_node_con_info[1],
                connection_user=original_node_con_info[2],
                connection_password=original_node_con_info[3],
                ca_key=original_node_con_info[4]
            )

            new_node_con_info = remote_cluster_instance.generate_connection_info()
            original_cluster.add_node_configuration(node_name=new_node_con_info[0],
                                                    ip_address=new_node_con_info[1],
                                                    connection_user=new_node_con_info[2],
                                                    connection_password=new_node_con_info[3],
                                                    ca_key=new_node_con_info[4])

            # Create client certificates for libvirt for the new node to connect to the
            # current cluster node
            new_node_cert_gen = new_node_cert_gen_factory.get_cert_generator(original_node)
            remote_node.annotate_object(new_node_cert_gen)
            csr = new_node_cert_gen.generate_csr()
            original_node_cert_gen_factory = original_node_remote.get_connection(
                'certificate_generator_factory')
            original_node_cert_gen = original_node_cert_gen_factory.get_cert_generator(
                node_config['hostname'], remote=True
            )
            original_node_remote.annotate_object(original_node_cert_gen)
            pub_key = original_node_cert_gen.sign_csr(csr)
            new_node_cert_gen.add_public_key(pub_key)

            # Create client certificate for libvirt for the current cluster node to connect
            # to the new node
            original_node_cert_gen = original_node_cert_gen_factory.get_cert_generator(node_config[
                                                                                       'hostname'])
            original_node_remote.annotate_object(original_node_cert_gen)

            # Generate CSR
            csr = original_node_cert_gen.generate_csr()

            # Sign CSR
            new_node_cert_gen = new_node_cert_gen_factory.get_cert_generator(
                original_node, remote=True)
            remote_node.annotate_object(new_node_cert_gen)
            pub_key = new_node_cert_gen.sign_csr(csr)

            # Add public key to original node
            original_node_cert_gen.add_public_key(pub_key)

        # If Drbd is enabled on the local node, configure/enable it on the remote node
        self.sync_drbd_config(remote_node)

        # Sync users
        self.sync_users(remote_node)

        # Sync networks
        self.sync_networks(remote_node)

        # Sync global permissions
        self.sync_permissions(remote_node)

        # Sync storage backends
        self.sync_storage_backends(remote_node, location_overrides=location_overrides)

        # Sync VMs
        self.sync_virtual_machines(remote_node)

        # Sync MCVirt configurations
        self.sync_config(remote_node)

    def sync_drbd_config(self, remote_node):
        """Sync the DRBD config from the local node to the remote one."""
        Syslogger.logger().debug('Syncing DRBD config')
        if self.po__get_registered_object('node_drbd').is_enabled():
            remote_drbd = remote_node.get_connection('node_drbd')
            remote_drbd.enable(secret=MCVirtConfig().get_config()['drbd']['secret'])

    def sync_users(self, remote_node):
        """Synchronise the local users with the remote node."""
        # Remove all users on the remote node
        remote_user_factory = remote_node.get_connection('user_factory')
        for remote_user in remote_user_factory.get_all_users():
            remote_node.annotate_object(remote_user)
            if remote_user.is_locally_managed():
                remote_user.delete()

        user_factory = self.po__get_registered_object('user_factory')
        for user in user_factory.get_all_users():
            if user.is_locally_managed():
                remote_user_factory.add_config(user.get_username(), user.get_config())

    def sync_networks(self, remote_object):
        """Add the local networks to the remote node."""
        network_factory = self.po__get_registered_object('network_factory')

        # Remove all networks from remote node
        remote_network_factory = remote_object.get_connection('network_factory')
        for remote_network in remote_network_factory.get_all_network_objects():
            remote_object.annotate_object(remote_network)
            remote_network.delete()

        for network in network_factory.get_all_network_objects():
            remote_network_factory.create(name=network.get_name(),
                                          physical_interface=network.get_adapter())

    def sync_permissions(self, remote_object):
        """Duplicate the global permissions on the local node onto the remote node."""
        auth_instance = self.po__get_registered_object('auth')
        remote_auth_instance = remote_object.get_connection('auth')
        remote_user_factory = remote_object.get_connection('user_factory')

        # Sync superusers
        for superuser in auth_instance.get_superusers():
            remote_user_object = remote_user_factory.get_user_by_username(superuser)
            remote_object.annotate_object(remote_user_object)
            if not remote_user_object.is_superuser():
                remote_auth_instance.add_superuser(remote_user_object)

        group_factory = self.po__get_registered_object('group_factory')
        remote_group_factory = remote_object.get_connection('group_factory')

        # Sync group configuration
        remote_group_factory.set_config(group_factory.get_config())

    def sync_storage_backends(self, remote_object, location_overrides):
        """Duplicate the storage backend objects to the new node."""
        # Sync entire storage backend configuration to new node
        Syslogger.logger().debug('Syncing storage backends')
        storage_factory = self.po__get_registered_object('storage_factory')
        remote_storage_factory = remote_object.get_connection('storage_factory')
        storage_factory_config = storage_factory.get_config()

        remote_mcvirt_config_obj = remote_object.get_connection('mcvirt_config')
        remote_config = remote_mcvirt_config_obj.get_config_remote()

        # Update remote MCVirt config with entire storage backend config
        remote_config[storage_factory.STORAGE_CONFIG_KEY] = storage_factory_config
        remote_mcvirt_config_obj.manual_update_config(
            remote_config,
            'Replicate storage backend configuration to new node')

        # Add new node to storage backends that have a default location
        for storage_backend in storage_factory.get_all():
            # Determine if storage backend has a default location
            location = (location_overrides[storage_backend.name]
                        if storage_backend.name in location_overrides
                        else storage_backend.get_location(return_default=True))
            if location:
                Syslogger.logger().debug('Adding storage backend %s to new node' %
                                         storage_backend.name)
                try:
                    remote_storage_factory.node_pre_check(
                        storage_type=storage_backend.storage_type,
                        location=location)
                except Exception, exc:
                    Syslogger.logger().warning(
                        'Storage backend location does not exist on node: %s %s %s %s' %
                        (storage_backend.name, remote_object.name, location, str(exc)))
                    # Ignore and continue with next storage backend
                    continue
                # Since pre check passed, add the node to the storage backends
                storage_backend.add_node(remote_object.name)

    def sync_virtual_machines(self, remote_object):
        """Duplicate the VM configurations on the local node onto the remote node."""
        # Syncronise hard drive configurations and virtual machine configurations
        hard_drive_config = HardDriveConfig.get_global_config()
        virtual_machine_config = VirtualMachineConfig.get_global_config()

        remote_mcvirt_config_obj = remote_object.get_connection('mcvirt_config')
        remote_config = remote_mcvirt_config_obj.get_config_remote()
        remote_config['hard_drives'] = hard_drive_config
        remote_config['virtual_machines'] = virtual_machine_config

        # Update hard drive and virtual machinie configuration to remote node
        remote_mcvirt_config_obj.manual_update_config(remote_config,
                                                      ('Update HDD/VM configuration after'
                                                       ' joining node to cluster.'))

    def sync_config(self, remote_connection):
        """Sync MCVirt configuration."""
        local_config = self.po__get_registered_object('mcvirt_config')().get_config()
        remote_mcvirt_config_obj = remote_connection.get_connection('mcvirt_config')
        remote_config = remote_mcvirt_config_obj.get_config_remote()

        # Update Git and LDAP configuration to remote node
        remote_config['git'] = local_config['git']
        remote_config['ldap'] = local_config['ldap']
        remote_mcvirt_config_obj.manual_update_config(remote_config,
                                                      ('Update LDAP/Git configuration after'
                                                       ' joining node to cluster.'))

    def check_remote_machine(self, remote_connection, location_overrides):
        """Perform checks on the remote node to ensure that there will be
        no object conflicts when syncing the Network and VM configurations
        """
        # Ensure that the remote node has no cluster nodes
        remote_cluster = remote_connection.get_connection('cluster')
        if len(remote_cluster.get_nodes(return_all=True)):
            raise RemoteObjectConflict('Remote node already part of a cluster')

        # Get local and remote storage factories
        storage_factory = self.po__get_registered_object('storage_factory')
        remote_storage_factory = remote_connection.get_connection('storage_factory')

        # Ensure that all global storage backends (which will be replicated to new
        # node) exist on the remote node. Also check any locations specified in overrides
        storage_backends = storage_factory.get_all(global_=True)
        for name in location_overrides.keys():
            if name not in [storage_backend.name for storage_backend in storage_backends]:
                storage_backends.append(storage_factory.get_object(name=name))

        # Check each of the backends will MUST be added to the node
        for storage_backend in storage_backends:
            Syslogger.logger().debug('Checking storage backend: %s' % storage_backend.name)
            # Determine location, either the default or override, if specified
            location = (location_overrides[storage_backend.name]
                        if storage_backend.name in location_overrides
                        else storage_backend.get_location(default=True))
            # Check that volume group/directory exists on remote machine
            Syslogger.logger().debug('Validating storage backend')
            remote_storage_factory.node_pre_check(
                storage_type=storage_backend.storage_type,
                location=location)

        # Determine if any of the local networks/VMs exist on the remote node
        remote_network_factory = remote_connection.get_connection('network_factory')

        # Check that each of the interfaces, used for the networks, is present on the
        # remote node
        network_factory = self.po__get_registered_object('network_factory')
        for local_network in network_factory.get_all_network_objects():
            remote_network_factory.pre_check_network(local_network.get_name(),
                                                     local_network.get_adapter())

        # Determine if there are any VMs on the remote node
        remote_virtual_machine_factory = remote_connection.get_connection(
            'virtual_machine_factory')
        if len(remote_virtual_machine_factory.get_all_virtual_machines()):
            raise RemoteObjectConflict(('Target node contains VMs.'
                                        ' These must be removed before adding to a cluster'))

        # If Drbd is enabled on the local machine, ensure it is installed on the remote machine
        # and is not already enabled
        remote_node_drbd = remote_connection.get_connection('node_drbd')

        if self.po__get_registered_object('node_drbd').is_enabled():
            if not remote_node_drbd.is_installed():
                raise DrbdNotInstalledException('Drbd is not installed on the remote node')

        if remote_node_drbd.is_enabled():
            raise DrbdNotInstalledException('Drbd is already enabled on the remote node')

    @Expose(locking=True)
    def remove_node(self, node_name_to_remove):
        """Remove a node from the MCVirt cluster."""
        # Ensure the user has privileges to manage the cluster
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)

        # Ensure node exists
        self.ensure_node_exists(node_name_to_remove)

        # Check for any VMs that the node, to be removed, is available to
        vm_factory = self.po__get_registered_object('virtual_machine_factory')
        all_vm_objects = vm_factory.get_all_virtual_machines()
        for vm_object in all_vm_objects:
            vm_available_nodes = vm_object.getAvailableNodes()
            if len(vm_available_nodes) > 1 and node_name_to_remove in vm_available_nodes:
                raise RemoteObjectConflict('The remote node is available to VM: %s' %
                                           vm_object.get_name())

        # Ensure that node can be removed from any storage backends that it is
        # part of
        for storage_backend in self.po__get_registered_object('storage_factory').get_all(
                nodes=[node_name_to_remove]):
            storage_backend.ensure_can_remove_node(node_name_to_remove)

        # Get a list of remote cluster nodes that will remain in the cluster.
        all_nodes = self.get_nodes(return_all=True)
        all_nodes.remove(node_name_to_remove)

        def remove_vm(remote_connection, vm_name):
            """Remove VM from remote node."""
            if remote_connection is not None:
                remote_vm_factory = remote_connection.get_connection('virtual_machine_factory')
                remote_vm = remote_vm_factory.get_virtual_machine_by_name(vm_name)
                remote_connection.annotate_object(remote_vm)
                remote_vm.delete(local_only=True)

        # Remove any VMs that are only present on the remote node
        node_to_remove_con = self.get_remote_node(node_name_to_remove)
        for vm_object in all_vm_objects:
            if vm_object.getAvailableNodes() == [node_name_to_remove]:
                vm_object.delete(local_only=True)
                self.run_remote_command(callback_method=remove_vm, nodes=all_nodes,
                                        kwargs={'vm_name': vm_object.get_name()})
            else:
                remove_vm(node_to_remove_con, vm_object.get_name())

        # Remove node from any storage backends that it's part of
        for storage_backend in self.po__get_registered_object('storage_factory').get_all(
                nodes=[node_name_to_remove]):
            storage_backend.remove_node(node_name_to_remove)

        # Remove the SSL certificates from the other nodes
        self._remove_node_ssl_certificates(node_name_to_remove)

    @Expose()
    def remove_node_ssl_certificates(self, remote_node):
        """Exposed method for _remove_node_ssl_certificates."""
        self.po__get_registered_object('auth').check_user_type('ClusterUser')
        self._remove_node_ssl_certificates(remote_node)

    def _remove_node_ssl_certificates(self, remote_node):
        """Remove the SSL certificates relating to a node
        that is being removed from the cluster
        """
        if self.po__is_cluster_master:
            def remove_auth(node_connection, remove_nodes):
                """Removes the SSL certificates for the remote node."""
                remote_cluster = node_connection.get_connection('cluster')
                for remove_node in remove_nodes:
                    remote_cluster.remove_node_ssl_certificates(remove_node)

            # For all remaining nodes in the cluster, remove all SSL certificates
            # and cluster user for node being removed.
            other_nodes = self.get_nodes()
            other_nodes.remove(remote_node)

            self.run_remote_command(callback_method=remove_auth, nodes=other_nodes,
                                    kwargs={'remove_nodes': [remote_node]})

            # Remove Credentials for all nodes in cluster from node being removed
            other_nodes.append(get_hostname())
            self.run_remote_command(callback_method=remove_auth, nodes=[remote_node],
                                    kwargs={'remove_nodes': other_nodes})

        # Remove authentication from the local node to the node to be removed
        cert_generator = self.po__get_registered_object(
            'certificate_generator_factory'
        ).get_cert_generator(remote_node)
        cert_generator.remove_certificates()

        # Remove local cluster user
        user_factory = self.po__get_registered_object('user_factory')
        user = user_factory.get_cluster_user_by_node(remote_node)
        user.delete()

        # Remove configuration for remote node from local config
        self.remove_node_configuration(remote_node)

    def get_cluster_ip_address(self):
        """Return the cluster IP address of the local node."""
        cluster_config = self.get_cluster_config()
        return cluster_config['cluster_ip']

    def get_remote_node(self, node, ignore_cluster_master=False, set_cluster_master=False):
        """Obtain a Remote object for a node, caching the object."""
        if not self.po__is_cluster_master and not ignore_cluster_master:
            raise ClusterNotInitialisedException('Cannot get remote node %s' % node +
                                                 ' as the cluster is not initialised')

        node_config = self.get_node_config(node)
        try:
            node_object = Node(
                node, node_config,
                cluster_master=(set_cluster_master if set_cluster_master else None)
            )
        except Exception, exc:
            if not self.po__cluster_disabled:
                Syslogger.logger().error('Could not connect to node \'%s\':\n%s' %
                                         (node, str(exc)))
                raise InaccessibleNodeException('Cannot connect to node \'%s\'' % node)
            else:
                self.add_inaccessible_node(node)
                Syslogger.logger().error('Cannot connect to node: %s (Ignored)' % node)
            node_object = None
        return node_object

    def get_cluster_config(self):
        """Get the MCVirt cluster configuration."""
        return MCVirtConfig().get_config()['cluster']

    def get_node_config(self, node, include_local=False):
        """Return the configuration for a node."""
        self.ensure_node_exists(node, include_local=True)
        if node == get_hostname():
            return {
                'ip_address': self.get_cluster_ip_address()
            }
        else:
            return self.get_cluster_config()['nodes'][node]

    def set_context_defaults(self):
        """Set the cluster-specific pyro default context."""
        # Reset list of failing nodes, as this state is only
        # persisted for a single connection.
        Pyro4.current_context.inaccessible_nodes = []

    @property
    def inaccessible_nodes(self):
        """Return list of inaccessible nodes."""
        if self.po__is_pyro_initialised:
            return Pyro4.current_context.inaccessible_nodes
        else:
            return []

    def add_inaccessible_node(self, node):
        """Add node to list of inaccessible nodes."""
        if self.po__is_pyro_initialised:
            if node not in self.inaccessible_nodes:
                Pyro4.current_context.inaccessible_nodes.append(node)
        else:
            Syslogger.logger().warn(
                'Could not register inaccessible node as Pyro is not initialised')

    @Expose()
    def get_nodes(self, return_all=False, include_local=False):
        """Return an array of node configurations."""
        cluster_config = self.get_cluster_config()
        nodes = cluster_config['nodes'].keys()

        # If requesting nodes (not return_all) and is not
        # the cluster master, just return the local node.
        # This assumes that return_all is being used for configuration,
        # so without it, it's being assumed that the response
        # is being used for executing a command on a remote node,
        # which shouldn't be performed if not the cluster master
        if not return_all and not self.po__is_cluster_master:
            Syslogger.logger().warn(
                'Requesting cluster get_nodes: is not cluster master and '
                'is not return_all')
            return [get_hostname()]

        if self.po__cluster_disabled and not return_all:
            for node in self.inaccessible_nodes:
                if node in nodes:
                    nodes.remove(node)
        if include_local:
            nodes.append(get_hostname())
        return nodes

    def run_remote_command(self, callback_method, nodes=None, args=[], kwargs={},
                           ignore_cluster_master=False, node=None):
        """Run a remote command on all (or a given list of) remote nodes."""
        return_data = {}

        # If the user has not specified a list of nodes, obtain all remote nodes
        if nodes is None and node is None:
            # Obtain all nodes, without specifying 'return_all', meaning that if the cluster
            # is offline, no nodes will be returned.
            nodes = self.get_nodes(return_all=False, include_local=False)

        # If nodes is empty, set to empty array
        elif nodes is None:
            nodes = []

        # If a single node has been defined, ensure it's not already defined
        # in nodes list and append
        if node is not None and node not in nodes:
            nodes.append(node)

        # Iterate through each node
        for node in nodes:
            # Obtain connection to node
            node_object = self.get_remote_node(node, ignore_cluster_master=ignore_cluster_master)

            # If node object wasn't returned as None (which happends when the node is
            # unavailable and cluster has been ignored)
            if node_object is not None:
                # Run the callback method, providing the custom args and kwargs, capturing
                # the output in return_data dict
                return_data[node] = callback_method(node_object, *args, **kwargs)

        # Return dict of returned values
        return return_data

    def check_node_exists(self, node_name, include_local=False):
        """Determine if a node is already present in the cluster."""
        return node_name in self.get_nodes(return_all=True, include_local=include_local)

    def ensure_node_exists(self, node, include_local=False):
        """Check if node exists and throws exception if it does not."""
        if not self.check_node_exists(node_name=node, include_local=include_local):
            raise NodeDoesNotExistException('Node %s does not exist' % node)

    def remove_node_configuration(self, node_name):
        """Remove an MCVirt node from the configuration and regenerates
        authorized_keys file
        """
        def remove_node_config(mcvirt_config):
            """Remove node config from MCVirt config."""
            del mcvirt_config['cluster']['nodes'][node_name]
        MCVirtConfig().update_config(remove_node_config)

    def get_compatible_nodes(self, storage_backends, networks):
        """Determine a list of available networks, based on required storage
           backends and networks."""
        node_lists = [storage_backend.nodes for storage_backend in storage_backends] + \
                     [network.nodes for network in networks]

        available_nodes = self.get_nodes(include_local=True, return_all=True)
        for node in available_nodes:
            for node_list in node_lists:
                if node not in node_list:
                    available_nodes.remove(node)

        return available_nodes

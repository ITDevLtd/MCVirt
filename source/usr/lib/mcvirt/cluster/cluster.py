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

import os.path
import json
import socket
import base64
import Pyro4
from texttable import Texttable

from mcvirt.rpc.ssl_socket import SSLSocket
from mcvirt.utils import get_hostname
from mcvirt.exceptions import (NodeAlreadyPresent, NodeDoesNotExistException,
                               RemoteObjectConflict, ClusterNotInitialisedException,
                               InvalidConnectionString, CAFileAlreadyExists,
                               CouldNotConnectToNodeException,
                               MissingConfigurationException)
from mcvirt.auth.auth import Auth
from mcvirt.system import System
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.factory import Factory as UserFactory
from mcvirt.auth.connection_user import ConnectionUser
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.client.rpc import Connection
from mcvirt.node.network.factory import Factory as NetworkFactory
from mcvirt.rpc.lock import lockingMethod
from remote import Node
from mcvirt.rpc.pyro_object import PyroObject


class Cluster(PyroObject):
    """Class to perform node management within the MCVirt cluster"""

    @staticmethod
    def getHostname():
        """Returns the hostname of the system"""
        return socket.gethostname()

    @Pyro4.expose()
    def generateConnectionInfo(self):
        """Generates required information to connect to this node from a remote node"""
        # Ensure user has required permissions
        self.mcvirt_instance.getAuthObject().assertPermission(
            PERMISSIONS.MANAGE_CLUSTER
        )

        # Determine IP address
        ip_address = self.getClusterIpAddress()
        if not ip_address:
            raise MissingConfigurationException('IP address has not yet been configured')

        # Create connection user
        user_factory = UserFactory(self.mcvirt_instance)
        connection_username, connection_password = user_factory.generate_user(ConnectionUser)
        return [get_hostname(), self.getClusterIpAddress(),
                connection_username, connection_password,
                SSLSocket.get_ca_contents()]

    @Pyro4.expose()
    def getConnectionString(self):
        """Generate a string to connect to this node from a remote cluster"""
        # Only superusers can generate a connection string
        self.mcvirt_instance.getAuthObject().assertPermission(
            PERMISSIONS.MANAGE_CLUSTER
        )

        # Generate dict with connection information. Convert to JSON and base64 encode
        connection_info = self.generateConnectionInfo()
        connection_info_dict = {
            'hostname': connection_info[0],
            'ip_address': connection_info[1],
            'username': connection_info[2],
            'password': connection_info[3],
            'ca_cert': connection_info[4]
        }
        connection_info_json = json.dumps(connection_info_dict)
        return base64.b64encode(connection_info_json)

    def __init__(self, mcvirt_instance):
        """Sets member variables"""
        self.mcvirt_instance = mcvirt_instance

    @Pyro4.expose()
    def printInfo(self):
        """Prints information about the nodes in the cluster"""
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Node', 'IP Address', 'Status'))
        # Add this node to the table
        table.add_row((get_hostname(), self.getClusterIpAddress(),
                       'Local'))

        # Add remote nodes
        for node in self.getNodes(return_all=True):
            node_config = self.getNodeConfig(node)
            node_status = 'Unreachable'
            try:
                self.getRemoteNode(node)
                node_status = 'Connected'
            except CouldNotConnectToNodeException:
                pass
            table.add_row((node, node_config['ip_address'],
                           node_status))
        return table.draw()

    @Pyro4.expose()
    def addNodeConfiguration(self, node_name, ip_address,
                             connection_user, connection_password,
                             ca_key, ca_check=True):
        """Adds MCVirt node to configuration and generates SSH
        authorized_keys file"""
        # Create CA file
        SSLSocket.add_ca_file(node_name, ca_key, check_exists=ca_check)

        # Connec to node and obtain cluster user
        remote = Connection(username=connection_user, password=connection_password,
                            host=node_name)
        remote_user_factory = remote.getConnection('user_factory')
        connection_user = remote_user_factory.get_user_by_username(connection_user)
        remote.annotateObject(connection_user)
        username, password = connection_user.createClusterUser(host=get_hostname())

        # Add node to configuration file
        def addNode(mcvirt_config):
            mcvirt_config['cluster']['nodes'][node_name] = {
                'ip_address': ip_address,
                'username': username,
                'password': password
            }
        MCVirtConfig().updateConfig(addNode)

    @Pyro4.expose()
    @lockingMethod()
    def addNode(self, node_connection_string):
        """Connects to a remote MCVirt machine, shares SSH keys and clusters the machines"""
        # Ensure the user has privileges to manage the cluster
        self.mcvirt_instance.getAuthObject().assertPermission(PERMISSIONS.MANAGE_CLUSTER)

        try:
            config_json = base64.b64decode(node_connection_string)
            node_config = json.loads(config_json)
            assert 'username' in node_config and node_config['username']
            assert 'password' in node_config and node_config['password']
            assert 'ip_address' in node_config and node_config['ip_address']
            assert 'hostname' in node_config and node_config['hostname']
            assert 'ca_cert' in node_config and node_config['ca_cert']
        except:
            raise InvalidConnectionString('Connection string is invalid')

        # Determine if node is already connected to cluster
        if self.checkNodeExists(node_config['hostname']):
            raise NodeAlreadyPresent('Node %s is already connected to the cluster' % remote_host)

        # Create CA public key for machine
        SSLSocket.add_ca_file(node_config['hostname'], node_config['ca_cert'])

        # Check remote machine, to ensure it can be synced without any
        # conflicts
        remote = Connection(username=node_config['username'], password=node_config['password'],
                            host=node_config['hostname'])
        try:
            self.checkRemoteMachine(remote)
        except:
            raise
        remote = None
        original_cluster_nodes = self.getNodes()

        # Add remote node
        self.addNodeConfiguration(node_name=node_config['hostname'],
                                  ip_address=node_config['ip_address'],
                                  connection_user=node_config['username'],
                                  connection_password=node_config['password'],
                                  ca_key=node_config['ca_cert'],
                                  ca_check=False)

        # Obtain node connection to new node
        remote_node = self.getRemoteNode(node_config['hostname'])

        # Generate local connection user for new remote node
        local_connection_info = self.generateConnectionInfo()

        # Add the local node to the new remote node
        remote_cluster_instance = remote_node.getConnection('cluster')
        remote_cluster_instance.addNodeConfiguration(node_name=local_connection_info[0],
                                                     ip_address=local_connection_info[1],
                                                     connection_user=local_connection_info[2],
                                                     connection_password=local_connection_info[3],
                                                     ca_key=local_connection_info[4])

        # Sync credentials to/from old nodes in the clsuter
        for original_node in original_cluster_nodes:
            original_cluster = original_node.getConnection('cluster')
            original_node_con_info = original_cluster.generateConnectionInfo()
            remote_cluster_instance.addNodeConfiguration(node_name=original_node_con_info[0],
                                                         ip_address=original_node_con_info[1],
                                                         connection_user=original_node_con_info[2],
                                                         connection_password=original_node_con_info[3],
                                                         ca_key=original_node_con_info[4])
            new_node_con_info = remote_cluster_instance.generateConnectionInfo()
            original_cluster.addNodeConfiguration(node_name=new_node_con_info[0],
                                                  ip_address=new_node_con_info[1],
                                                  connection_user=new_node_con_info[2],
                                                  connection_password=new_node_con_info[3],
                                                  ca_key=new_node_con_info[4])

        # If DRBD is enabled on the local node, configure/enable it on the remote node
        if (self._get_registered_object('node_drbd').isEnabled()):
            remote_drbd = remote_node.getConnection('node_drbd')
            remote_drbd.enable()

        # Sync users
        self.sync_users(remote_node)

        # Sync networks
        self.sync_networks(remote_node)

        # Sync global permissions
        self.sync_permissions(remote_node)

        # Sync VMs
        self.sync_virtual_machines(remote_node)

    def sync_users(self, remote_node):
        """Syncronises the local users with the remote node"""
        # Remove all users on the remote node
        remote_user_factory = remote_node.getConnection('user_factory')
        for remote_user in remote_user_factory.get_all_users():
            remote_node.annotateObject(remote_user)
            remote_user.delete()

        user_factory = self._get_registered_object('user_factory')
        for user in user_factory.get_all_users():
            remote_user_factory.addConfig(user.getUsername(), user.getConfig())

    def sync_networks(self, remote_object):
        """Add the local networks to the remote node"""
        network_factory = self._get_registered_object('network_factory')

        # Remove all networks from remote node
        remote_network_factory = remote_object.getConnection('network_factory')
        for remote_network in remote_network_factory.getAllNetworkObjects():
            remote_object.annotateObject(remote_network)
            remote_network.delete()

        for network in network_factory.getAllNetworkObjects():
            remote_network_factory.create(name=network.getName(),
                                          physical_interface=network.getAdapter())

    def sync_permissions(self, remote_object):
        """Duplicates the global permissions on the local node onto the remote node"""
        auth_instance = self._get_registered_object('auth')
        remote_auth_instance = remote_object.getConnection('auth')
        remote_user_factory = remote_object.getConnection('user_factory')

        # Sync superusers
        for superuser in auth_instance.getSuperusers():
            remote_user_object = remote_user_factory.get_user_by_username(superuser)
            remote_object.annotateObject(remote_user_object)
            remote_auth_instance.addSuperuser(remote_user_object)

        # Iterate over the permission groups, adding all of the members to the group
        # on the remote node
        for group in auth_instance.getPermissionGroups():
            users = auth_instance.getUsersInPermissionGroup(group)
            for user in users:
                user_object = remote_user_factory.get_user_by_username(user)
                remote_object.annotateObject(user_object)
                remote_auth_instance.addUserPermissionGroup(group, user_object)

    def sync_virtual_machines(self, remote_object):
        """Duplicates the VM configurations on the local node onto the remote node"""
        virtual_machine_factory = self._get_registered_object('virtual_machine_factory')
        remote_virtual_machine_factory = remote_object.getConnection('virtual_machine_factory')

        # Obtain list of local VMs
        for vm_object in virtual_machine_factory.getAllVirtualMachines():
            remote_virtual_machine_object = remote_virtual_machine_factory.create(
                name=vm_object.getName(), cpu_cores=vm_object.getCPU(),
                memory_allocation=vm_object.getRAM(), hard_drives=[],
                node=vm_object.getNode(), available_nodes=vm_object.getAvailableNodes()
            )
            remote_object.annotateObject(remote_virtual_machine_object)

            # Add each of the disks to the VM
            remote_hard_drive_factory = remote_object.getConnection('hard_drive_factory')
            for hard_disk in vm_object.getHardDriveObjects():
                remote_hard_drive_object = remote_hard_drive_factory.getRemoteConfigObject(
                    hard_disk.getConfigObject()._dumpConfig()
                )
                remote_object.annotateObject(remote_hard_drive_object)
                remote_hard_drive_factory.addToVirtualMachine(remote_hard_drive_object)

            remote_network_factory = remote_object.getconnection('network_factory')
            for network_adapter in vm_object.getNetworkObjects():
                # Add network adapters to VM
                remote_network = remote_network_factory.getNetworkByName(network_adapter.getConnectedNetwork())
                remote_virtual_machine_object.createNetworkAdapter(
                    remote_network, mac_address=network_adapter.getMacAddress()
                )

            # Sync permissions to VM on remote node
            auth_instance = self._get_registered_object('auth')
            remote_auth_instance = remote_object.getConnection('auth')
            remote_user_factory = remote_object.getConnection('user_factory')
            for group in auth_instance.getPermissionGroups():
                users = auth_instance.getUsersInPermissionGroup(group, vm_object)
                for user in users:
                    user_object = remote_user_factory.get_user_by_username(user)
                    remote_object.annotateObject(user_object)
                    remote_auth_instance.addUserPermissionGroup(group, user_object,
                                                                remote_virtual_machine_object)

            # Set the VM node
            remote_virtual_machine_object.setNode(vm_object.getNode())

    def checkRemoteMachine(self, remote_connection):
        """Performs checks on the remote node to ensure that there will be
           no object conflicts when syncing the Network and VM configurations"""
        # Ensure that the remote node has no cluster nodes
        remote_cluster = remote_connection.getConnection('cluster')
        if len(remote_cluster.getNodes(return_all=True)):
            raise RemoteObjectConflict('Remote node already has nodes attached')

        # Determine if any of the local networks/VMs exist on the remote node
        remote_network_factory = remote_connection.getConnection('network_factory')

        # Check that each of the interfaces, used for the networks, is present on the
        # remote node
        network_factory = NetworkFactory(self.mcvirt_instance)
        for local_network in network_factory.getAllNetworkObjects():
            if not remote_network_factory.interfaceExists(local_network.getAdapter()):
                raise RemoteObjectConflict('Network interface %s does not exist on remote node' %
                                           local_network.getAdapter())

        # Determine if there are any VMs on the remote node
        remote_virtual_machine_factory = remote_connection.getConnection('virtual_machine_factory')
        if len(remote_virtual_machine_factory.getAllVirtualMachines()):
            raise RemoteObjectConflict(('Target node contains VMs.'
                                        ' These must be removed before adding to a cluster'))

        # If DRBD is enabled on the local machine, ensure it is installed on the remote machine
        # and is not already enabled
        remote_node_drbd = remote_connection.getConnection('node_drbd')
        from mcvirt.node.drbd import (DRBD as NodeDRBD,
                                      DRBDNotInstalledException,
                                      DRBDAlreadyEnabled)

        if NodeDRBD.isEnabled():
            if not remote_node_drbd.isInstalled():
                raise DRBDNotInstalledException('DRBD is not installed on the remote node')

        if remote_node_drbd.isEnabled():
            raise DRBDNotInstalledException('DRBD is already enabled on the remote node')

    def removeNode(self, remote_host):
        """Removes a node from the MCVirt cluster"""
        # Ensure the user has privileges to manage the cluster
        self.mcvirt_instance.getAuthObject().assertPermission(PERMISSIONS.MANAGE_CLUSTER)

        # Ensure node exists
        self.ensureNodeExists(remote_host)

        # Check for any VMs that the target node is available to and where the node is not
        # the only not that the VM is available to
        all_vm_objects = self.mcvirt_instance.getAllVirtualMachineObjects()
        for vm_object in all_vm_objects:
            if ((vm_object.getStorageType() == 'DRBD' and
                 remote_host in vm_object.getAvailableNodes())):
                raise RemoteObjectConflict('The remote node is available to VM: %s' %
                                           vm_object.getName())

        all_nodes = self.getNodes(return_all=True)
        all_nodes.remove(remote_host)

        # Remove any VMs that are only present on the remote node
        for vm_object in all_vm_objects:
            if ((vm_object.getStorageType() == 'Local' and
                 vm_object.getAvailableNodes() == [remote_host])):
                vm_object.delete(remove_data=True, local_only=True)
                cluster.runRemoteCommand('virtual_machine-delete',
                                         {'vm_name': vm_object.getName(),
                                          'remove_data': True},
                                         nodes=all_nodes)

        if (remote_host not in self.getFailedNodes()):
            remote = self.getRemoteNode(remote_host)

            # Remove any VMs from the remote node that the node is not able to run
            all_vm_objects = self.mcvirt_instance.getAllVirtualMachineObjects()
            for vm_object in all_vm_objects:
                if (vm_object.getAvailableNodes() != [remote_host]):
                    remote.runRemoteCommand('virtual_machine-delete',
                                            {'vm_name': vm_object.getName(),
                                             'remove_data': True})

            # Remove all nodes in the cluster from the remote node
            all_nodes.append(get_hostname())
            for node in all_nodes:
                remote.runRemoteCommand('cluster-cluster-removeNodeConfiguration',
                                        {'node': node})

        # Remove remote node from local configuration
        self.removeNodeConfiguration(remote_host)

        # Remove the node from the remote node connections, if it exists
        if (remote_host in self.mcvirt_instance.remote_nodes):
            del self.mcvirt_instance.remote_nodes[remote_host]

        # Remove the node from the rest of the nodes in the cluster
        self.runRemoteCommand('cluster-cluster-removeNodeConfiguration',
                              {'node': remote_host})

    def getClusterIpAddress(self):
        """Returns the cluster IP address of the local node"""
        cluster_config = self.getClusterConfig()
        return cluster_config['cluster_ip']

    def getRemoteNode(self, node):
        """Obtains a Remote object for a node, caching the object"""
        if not self._is_cluster_master:
            raise ClusterNotInitialisedException('Cannot get remote node %s' % node +
                                                 ' as the cluster is not initialised')

        node_config = self.getNodeConfig(node)
        try:
            node_object = Node(node, node_config)
        except:
            if not self._cluster_disabled:
                raise
        return Node(node, node_config)

    def getClusterConfig(self):
        """Gets the MCVirt cluster configuration"""
        return MCVirtConfig().getConfig()['cluster']

    def getNodeConfig(self, node):
        """Returns the configuration for a node"""
        self.ensureNodeExists(node)
        return self.getClusterConfig()['nodes'][node]

    @Pyro4.expose()
    def getNodes(self, return_all=False):
        """Returns an array of node configurations"""
        cluster_config = self.getClusterConfig()
        nodes = cluster_config['nodes'].keys()
        if self._cluster_disabled and not return_all:
            for node in nodes:
                if node in self.getFailedNodes():
                    nodes.remove(node)
        return nodes

    def runRemoteCommand(self, callback_method, nodes=None):
        """Runs a remote command on all (or a given list of) remote nodes"""
        return_data = {}

        # If the user has not specified a list of nodes, obtain all remote nodes
        if nodes is None:
            nodes = self.getNodes()
        for node in nodes:
            node_object = self.getRemoteNode(node)
            return_data[node] = callback_method(node)
        return return_data

    def checkNodeExists(self, node_name):
        """Determines if a node is already present in the cluster"""
        return (node_name in self.getNodes(return_all=True))

    def ensureNodeExists(self, node):
        """Checks if node exists and throws exception if it does not"""
        if not self.checkNodeExists(node):
            raise NodeDoesNotExistException('Node %s does not exist' % node)

    def removeNodeConfiguration(self, node_name):
        """Removes an MCVirt node from the configuration and regenerates
        authorized_keys file"""
        def removeNodeConfig(mcvirt_config):
            del(mcvirt_config['cluster']['nodes'][node_name])
        MCVirtConfig().updateConfig(removeNodeConfig)

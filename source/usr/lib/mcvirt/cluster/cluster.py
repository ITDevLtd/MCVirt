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

from mcvirt.auth.auth import Auth
from mcvirt.mcvirt import MCVirtException
from mcvirt.system import System
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.auth.factory import Factory as UserFactory
from mcvirt.auth.connection_user import ConnectionUser


class NodeAlreadyPresent(MCVirtException):
    """Node being added is already connected to cluster"""
    pass


class NodeDoesNotExistException(MCVirtException):
    """The node does not exist"""
    pass


class RemoteObjectConflict(MCVirtException):
    """The remote node contains an object that will cause conflict when syncing"""
    pass


class ClusterNotInitialisedException(MCVirtException):
    """The cluster has not been initialised, so cannot connect to the remote node"""
    pass


class Cluster(object):
    """Class to perform node management within the MCVirt cluster"""

    @staticmethod
    def getHostname():
        """Returns the hostname of the system"""
        return socket.gethostname()

    @Pyro4.expose()
    def getConnectionString(self):
        # Only superusers can generate a connection string
        self.mcvirt_instance.getAuthObject().assertPermission(
            Auth.PERMISSIONS.MANAGE_CLUSTER
        )

        # Generate password and create connection user
        user_factory = UserFactory(self.mcvirt_instance)
        connection_username, connection_password = user_factory.generate_user(ConnectionUser)

        # Generate dict with connection information. Convert to JSON and base64 encode
        connection_info = {
            'username': connection_username,
            'password': connection_password,
            'ip_address': self.getClusterIpAddress(),
            'hostname': Cluster.getHostname()
        }
        connection_info_json = json.dumps(connection_info)
        return base64.b64encode(connection_info_json)

    def __init__(self, mcvirt_instance):
        """Sets member variables"""
        self.mcvirt_instance = mcvirt_instance

    def addNodeRemote(self, remote_host, remote_ip_address, remote_public_key):
        """Adds the machine to a remote cluster"""
        # Determine if node is already connected to cluster
        if (self.checkNodeExists(remote_host)):
            raise NodeAlreadyPresent('Node %s is already connected to the cluster' % remote_host)
        local_public_key = self.getSshPublicKey()
        self.addNodeConfiguration(remote_host, remote_ip_address, remote_public_key)
        return local_public_key

    def addNode(self, node_connection_string):
        """Connects to a remote MCVirt machine, shares SSH keys and clusters the machines"""
        from remote import Remote
        from mcvirt.node.drbd import DRBD
        # Ensure the user has privileges to manage the cluster
        self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_CLUSTER)

        # Determine if node is already connected to cluster
        if (self.checkNodeExists(remote_host)):
            raise NodeAlreadyPresent('Node %s is already connected to the cluster' % remote_host)

        # Check remote machine, to ensure it can be synced without any
        # conflicts
        remote = Remote(self, remote_host, remote_ip=remote_ip, password=password,
                        save_hostkey=True)
        try:
            self.checkRemoteMachine(remote)
        except:
            remote = None
            raise
        remote = None

        # Sync SSH keys
        local_public_key = self.getSshPublicKey()
        remote_public_key = self.configureRemoteMachine(remote_host, remote_ip,
                                                        password, local_public_key)
        all_pre_existing_cluster_nodes = self.getNodes(return_all=True)
        all_active_pre_existing_cluster_nodes = self.getNodes()

        # Add remote node to configuration
        self.addNodeConfiguration(remote_host, remote_ip, remote_public_key)

        # Connect to remote machine ensuring that it saves the host file
        remote = Remote(self, remote_host)

        # Add the local host key to the new remote node
        remote.runRemoteCommand('cluster-cluster-addHostKey', {'node': self.getHostname()})

        # Add the host key of current remote nodes to the new remote node
        for pre_existing_remote_node in all_pre_existing_cluster_nodes:
            node_config = self.getNodeConfig(pre_existing_remote_node)
            remote.runRemoteCommand('cluster-cluster-addNodeRemote',
                                    {'node': pre_existing_remote_node,
                                     'ip_address': node_config['ip_address'],
                                     'public_key': node_config['public_key']})

            if (pre_existing_remote_node in all_active_pre_existing_cluster_nodes):
                # Add new remote node to pre-existing remote node
                pre_existing_node_object = self.getRemoteNode(pre_existing_remote_node)
                pre_existing_node_object.runRemoteCommand('cluster-cluster-addNodeRemote',
                                                          {'node': remote_host,
                                                           'ip_address': remote_ip,
                                                           'public_key': remote_public_key})

                # Add hostkey of pre-existing remote node to new remote node
                remote.runRemoteCommand('cluster-cluster-addHostKey',
                                        {'node': pre_existing_remote_node})

                # Add hostkey of new remote node to pre-existing remote node
                pre_existing_node_object.runRemoteCommand('cluster-cluster-addHostKey',
                                                          {'node': remote_host})

        # If DRBD is enabled on the local node, configure/enable it on the remote node
        if (DRBD.isEnabled()):
            remote.runRemoteCommand('node-drbd-enable', {'secret': DRBD.getConfig()['secret']})

        # Sync networks
        self.syncNetworks(remote)

        # Sync global permissions
        self.syncPermissions(remote)

        # Sync VMs
        self.syncVirtualMachines(remote)

    def syncNetworks(self, remote_object):
        """Add the local networks to the remote node"""
        from mcvirt.node.network.network import Network
        local_networks = Network.getConfig()
        for network_name in local_networks.keys():
            remote_object.runRemoteCommand('node-network-create',
                                           {'network_name': network_name,
                                            'physical_interface': local_networks[network_name]})

    def syncPermissions(self, remote_object):
        """Duplicates the global permissions on the local node onto the remote node"""
        auth_object = Auth(self.mcvirt_instance)

        # Sync superusers
        for superuser in auth_object.getSuperusers():
            remote_object.runRemoteCommand('auth-addSuperuser', {'username': superuser,
                                                                 'ignore_duplicate': True})

        # Iterate over the permission groups, adding all of the members to the group
        # on the remote node
        for group in auth_object.getPermissionGroups():
            users = auth_object.getUsersInPermissionGroup(group)
            for user in users:
                remote_object.runRemoteCommand('auth-addUserPermissionGroup',
                                               {'permission_group': group,
                                                'username': user,
                                                'vm_name': None,
                                                'ignore_duplicate': True})

    def syncVirtualMachines(self, remote_object):
        """Duplicates the VM configurations on the local node onto the remote node"""
        from mcvirt.virtual_machine.virtual_machine import VirtualMachine

        # Obtain list of local VMs
        for vm_name in VirtualMachine.getAllVms(self.mcvirt_instance):
            vm_object = VirtualMachine(self.mcvirt_instance, vm_name)
            remote_object.runRemoteCommand('virtual_machine-create',
                                           {'vm_name': vm_object.getName(),
                                            'cpu_cores': vm_object.getCPU(),
                                            'memory_allocation': vm_object.getRAM(),
                                            'node': vm_object.getNode(),
                                            'available_nodes': vm_object.getAvailableNodes()})

            # Add each of the disks to the VM
            for hard_disk in vm_object.getHardDriveObjects():
                remote_object.runRemoteCommand('virtual_machine-hard_drive-addToVirtualMachine',
                                               {'config':
                                                hard_disk.getConfigObject()._dumpConfig()})

            for network_adapter in vm_object.getNetworkObjects():
                # Add network adapters to VM
                remote_object.runRemoteCommand('network_adapter-create',
                                               {'vm_name': vm_object.getName(),
                                                'network_name':
                                                network_adapter.getConnectedNetwork(),
                                                'mac_address': network_adapter.getMacAddress()})

            # Sync permissions to VM on remote node
            auth_object = Auth(self.mcvirt_instance)
            for group in auth_object.getPermissionGroups():
                users = auth_object.getUsersInPermissionGroup(group, vm_object)
                for user in users:
                    remote_object.runRemoteCommand('auth-addUserPermissionGroup',
                                                   {'permission_group': group,
                                                    'username': user,
                                                    'vm_name': vm_object.getName()})

            # Set the VM node
            remote_object.runRemoteCommand('virtual_machine-setNode',
                                           {'vm_name': vm_object.getName(),
                                            'node': vm_object.getNode()})

    def checkRemoteMachine(self, remote_object):
        """Performs checks on the remote node to ensure that there will be
           no object conflicts when syncing the Network and VM configurations"""
        # Determine if any of the local networks/VMs exist on the remote node
        remote_networks = remote_object.runRemoteCommand('node-network-getConfig', [])
        from mcvirt.node.network.network import Network
        for local_network in Network.getConfig().keys():
            if (local_network in remote_networks.keys()):
                raise RemoteObjectConflict('Remote node contains duplicate network: %s' %
                                           local_network)

        from mcvirt.virtual_machine.virtual_machine import VirtualMachine
        local_vms = VirtualMachine.getAllVms(self.mcvirt_instance)
        remote_vms = remote_object.runRemoteCommand('virtual_machine-getAllVms', [])
        for local_vm in local_vms:
            if (local_vm in remote_vms):
                raise RemoteObjectConflict('Remote node contains duplicate Virtual Machine: %s' %
                                           local_vm)

        # If DRBD is enabled on the local machine, ensure it is installed on the remote machine
        # and is not already enabled
        from mcvirt.node.drbd import (DRBD as NodeDRBD,
                                      DRBDNotInstalledException,
                                      DRBDAlreadyEnabled)
        if (NodeDRBD.isEnabled()):
            if (not remote_object.runRemoteCommand('node-drbd-isInstalled', [])):
                raise DRBDNotInstalledException('DRBD is not installed on the remote node')

            if (remote_object.runRemoteCommand('node-drbd-isEnabled', [])):
                raise DRBDNotInstalledException('DRBD is already enabled on the remote node')

    def removeNode(self, remote_host):
        """Removes a node from the MCVirt cluster"""
        # Ensure the user has privileges to manage the cluster
        self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_CLUSTER)

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
            all_nodes.append(self.getHostname())
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

    def getSshPublicKey(self):
        """Generates an SSH key pair for the local user if
        it doesn't already exist"""
        # Generate new ssh key if it doesn't already exist
        if (not os.path.exists(Cluster.SSH_PUBLIC_KEY) or
                not os.path.exists(Cluster.SSH_PRIVATE_KEY)):
            System.runCommand(('/usr/bin/ssh-keygen', '-t', 'rsa',
                               '-N', '', '-q', '-f', Cluster.SSH_PRIVATE_KEY))

        # Get contains of public key file
        with open(Cluster.SSH_PUBLIC_KEY, 'r') as f:
            public_key = str.strip(f.readline())
        return public_key

    def configureRemoteMachine(self, remote_host, remote_ip, password, local_public_key):
        """Connects to the remote machine and adds the local machine to the host"""
        from remote import Remote

        # Create a remote object, using the password and ensuring that the hostkey is saved
        remote_object = Remote(self, remote_host, save_hostkey=True,
                               remote_ip=remote_ip, password=password)

        # Run MCVirt on the remote machine to generate a SSH key and add the current host
        remote_public_key = remote_object.runRemoteCommand('cluster-cluster-addNodeRemote',
                                                           {'node': self.getHostname(),
                                                            'ip_address':
                                                            self.getClusterIpAddress(),
                                                            'public_key': local_public_key})

        # Delete the remote object to ensure it disconnects and saves the host key file
        remote_object = None

        return remote_public_key

    def connectNodes(self):
        """Obtains connection to each of the nodes"""
        from remote import CouldNotConnectToNodeException
        nodes = self.getNodes()
        for node in nodes:
            try:
                self.getRemoteNode(node)
            except CouldNotConnectToNodeException, e:
                if (self.mcvirt_instance.ignore_failed_nodes):
                    self.mcvirt_instance.failed_nodes.append(node)
                else:
                    raise

    def getRemoteNode(self, node):
        """Obtains a Remote object for a node, caching the object"""
        from mcvirt.cluster.remote import Remote

        if (not self.mcvirt_instance.initialise_nodes):
            raise ClusterNotInitialisedException('Cannot get remote node %s' % node +
                                                 ' as the cluster is not initialised')

        if (node not in self.mcvirt_instance.remote_nodes):
            self.mcvirt_instance.remote_nodes[node] = Remote(self, node)
        return self.mcvirt_instance.remote_nodes[node]

    def getClusterConfig(self):
        """Gets the MCVirt cluster configuration"""
        return MCVirtConfig().getConfig()['cluster']

    def getNodeConfig(self, node):
        """Returns the configuration for a node"""
        self.ensureNodeExists(node)
        return self.getClusterConfig()['nodes'][node]

    def getNodes(self, return_all=False):
        """Returns an array of node configurations"""
        cluster_config = self.getClusterConfig()
        nodes = cluster_config['nodes'].keys()
        if (self.mcvirt_instance.ignore_failed_nodes and not return_all):
            for node in nodes:
                if node in self.getFailedNodes():
                    nodes.remove(node)
        return nodes

    def getFailedNodes(self):
        """Returns an array of nodes that have failed to initialise and have been ignored"""
        return self.mcvirt_instance.failed_nodes

    def runRemoteCommand(self, action, arguments, nodes=None):
        """Runs a remote command on all (or a given list of) remote nodes"""
        return_data = {}

        # If the user has not specified a list of nodes, obtain all remote nodes
        if (nodes is None):
            nodes = self.getNodes()
        for node in nodes:
            if (node not in self.getFailedNodes()):
                node_object = self.getRemoteNode(node)
                return_data[node] = node_object.runRemoteCommand(action, arguments)
        return return_data

    def checkNodeExists(self, node_name):
        """Determines if a node is already present in the cluster"""
        return (node_name in self.getNodes(return_all=True))

    def ensureNodeExists(self, node):
        """Checks if node exists and throws exception if it does not"""
        if (not self.checkNodeExists(node)):
            raise NodeDoesNotExistException('Node %s does not exist' % node)

    def addNodeConfiguration(self, node_name, ip_address, public_key):
        """Adds MCVirt node to configuration and generates SSH
        authorized_keys file"""
        # Add node to configuration file
        def addNode(mcvirt_config):
            mcvirt_config['cluster']['nodes'][node_name] = {
                'ip_address': ip_address,
                'public_key': public_key
            }
        MCVirtConfig().updateConfig(addNode)
        self.buildAuthorizedKeysFile()

    def removeNodeConfiguration(self, node_name):
        """Removes an MCVirt node from the configuration and regenerates
        authorized_keys file"""
        def removeNodeConfig(mcvirt_config):
            del(mcvirt_config['cluster']['nodes'][node_name])
        MCVirtConfig().updateConfig(removeNodeConfig)
        self.buildAuthorizedKeysFile()

    def buildAuthorizedKeysFile(self):
        """Generates the authorized_keys file using the public keys
        from the MCVirt cluster node configuration"""
        with open(self.SSH_AUTHORIZED_KEYS_FILE, 'w') as text_file:
            text_file.write("# Generated by MCVirt\n")
            nodes = self.getNodes(return_all=True)
            for node_name in nodes:
                node_config = self.getNodeConfig(node_name)
                text_file.write("%s\n" % node_config['public_key'])

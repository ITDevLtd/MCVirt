#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import os.path
from mcvirt.auth import Auth
from mcvirt.mcvirt import McVirtException
from mcvirt.system import System
from mcvirt.mcvirt_config import McVirtConfig
import json
import socket

class NodeAlreadyPresent(McVirtException):
  """Node being added is already connected to cluster"""
  pass

class NodeDoesNotExistException(McVirtException):
  """The node does not exist"""
  pass

class RemoteObjectConflict(McVirtException):
  """The remote node contains an object that will cause conflict when syncing"""
  pass

class Cluster:
  """Class to perform node management within the McVirt cluster"""

  SSH_AUTHORIZED_KEYS_FILE = '/root/.ssh/authorized_keys'
  SSH_PRIVATE_KEY = '/root/.ssh/id_rsa'
  SSH_PUBLIC_KEY = '/root/.ssh/id_rsa.pub'
  SSH_KNOWN_HOSTS_FILE = '/root/.ssh/known_hosts'
  SSH_USER = 'root'

  @staticmethod
  def getHostname():
    """Returns the hostname of the system"""
    return socket.gethostname()

  def __init__(self, mcvirt_instance):
    """Sets member variables"""
    self.mcvirt_instance = mcvirt_instance

    # Connect to each of the nodes
    if (self.mcvirt_instance.initialise_nodes):
      self.connectNodes()

  def addNodeRemote(self, remote_host, remote_ip_address, remote_public_key):
    """Adds the machine to a remote cluster"""
    # Determine if node is already connected to cluster
    if (self.checkNodeExists(remote_host)):
      raise NodeAlreadyPresent('Node %s is already connected to the cluster' % remote_host)
    local_public_key = self.getSshPublicKey()
    self.addNodeConfiguration(remote_host, remote_ip_address, remote_public_key)
    return local_public_key

  def addNode(self, remote_host, remote_ip, password):
    """Connects to a remote McVirt machine, shares SSH keys and clusters the machines"""
    from remote import Remote
    # Ensure the user has privileges to manage the cluster
    self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_CLUSTER)

    # Determine if node is already connected to cluster
    if (self.checkNodeExists(remote_host)):
      raise NodeAlreadyPresent('Node %s is already connected to the cluster' % remote_host)

    # Check remote machine, to ensure it can be synced without any
    # conflicts
    remote = Remote(self, remote_host, remote_ip=remote_ip, password=password, save_hostkey=True)
    self.checkRemoteMachine(remote)
    remote = None

    # Sync SSH keys
    local_public_key = self.getSshPublicKey()
    remote_public_key = self.configureRemoteMachine(remote_host, remote_ip, password, local_public_key)

    # Add remote node to configuration
    self.addNodeConfiguration(remote_host, remote_ip, remote_public_key)

    # Connect to remote machine ensuring that it saves the host file
    remote = Remote(self, remote_host)
    remote.runRemoteCommand('cluster-cluster-addHostKey', {'node': self.getHostname()})

    # Sync networks
    self.syncNetworks(remote)

    # Sync global permissions
    self.syncPermissions(remote)

    # Sync VMs
    self.syncVirtualMachines(remote)

  def syncNetworks(self, remote_object):
    """Add the local networks to the remote node"""
    from mcvirt.node.network import Network
    local_networks = Network.getConfig()
    for network_name in local_networks.keys():
      remote_object.runRemoteCommand('node-network-create', {'network_name': network_name,
                                                             'physical_interface': local_networks[network_name]})

  def syncPermissions(self, remote_object):
    """Duplicates the global permissions on the local node onto the remote node"""
    from mcvirt.auth import Auth
    auth_object = Auth()

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

      for network_adapter in vm_object.getNetworkObjects():
        # Add network adapters to VM
        remote_object.runRemoteCommand('network_adapter-create',
                                       {'vm_name': vm_object.getName(),
                                        'network_name': network_adapter.getConnectedNetwork(),
                                        'mac_address': network_adapter.getMacAddress()})

      # Sync permissions to VM on remote node
      auth_object = Auth()
      for group in auth_object.getPermissionGroups():
        users = auth_object.getUsersInPermissionGroup(group, vm_object)
        for user in users:
          remote_object.runRemoteCommand('auth-addUserPermissionGroup',
                                         {'permission_group': group,
                                          'username': user,
                                          'vm_name': vm_object.getName()})


  def checkRemoteMachine(self, remote_object):
    """Performs checks on the remote node to ensure that there will be
       no object conflicts when syncing the Network and VM configurations"""
    # Determine if any of the local networks/VMs exist on the remote node
    remote_networks = remote_object.runRemoteCommand('node-network-getConfig', [])
    from mcvirt.node.network import Network
    for local_network in Network.getConfig().keys():
      if (local_network in remote_networks.keys()):
        raise RemoteObjectConflict('Remote node contains duplicate network: %s' % local_network)

    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    local_vms = VirtualMachine.getAllVms(self.mcvirt_instance)
    remote_vms = remote_object.runRemoteCommand('virtual_machine-getAllVms', [])
    for local_vm in local_vms:
      if (local_vm in remote_vms):
        raise RemoteObjectConflict('Remote node contains duplicate Virtual Machine: %s' % local_vm)

  def removeNode(self, remote_host):
    """Removes a node from the McVirt cluster"""
    from remote import Remote

    # Ensure the user has privileges to manage the cluster
    self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_CLUSTER)
    remote = self.getRemoteNode(remote_host)
    remote.runRemoteCommand('cluster-cluster-removeNodeConfiguration', {'node': self.getHostname()})
    self.removeNodeConfiguration(remote_host)

  def getClusterIpAddress(self):
    """Returns the cluster IP address of the local node"""
    cluster_config = self.getClusterConfig()
    return cluster_config['cluster_ip']

  def getSshPublicKey(self):
    """Generates an SSH key pair for the local user if
    it doesn't already exist"""
    # Generate new ssh key if it doesn't already exist
    if (not os.path.exists(Cluster.SSH_PUBLIC_KEY) or not os.path.exists(Cluster.SSH_PRIVATE_KEY)):
      System.runCommand(('/usr/bin/ssh-keygen', '-t', 'rsa', '-N', '', '-q', '-f', Cluster.SSH_PRIVATE_KEY))

    # Get contains of public key file
    with open(Cluster.SSH_PUBLIC_KEY, 'r') as f:
      public_key = str.strip(f.readline())
    return public_key

  def configureRemoteMachine(self, remote_host, remote_ip, password, local_public_key):
    """Connects to the remote machine and adds the local machine to the host"""
    from remote import Remote

    # Create a remote object, using the password and ensuring that the hostkey is saved
    remote_object = Remote(self, remote_host, save_hostkey=True, remote_ip=remote_ip, password=password)

    # Run McVirt on the remote machine to generate a SSH key and add the current host
    remote_public_key = remote_object.runRemoteCommand('cluster-cluster-addNodeRemote', {'node': self.getHostname(),
      'ip_address': self.getClusterIpAddress(), 'public_key': local_public_key})

    # Delete the remote object to ensure it disconnects and saves the host key file
    remote_object = None

    return remote_public_key

  def connectNodes(self):
    """Obtains connection to each of the nodes"""
    for node in self.getNodes():
      self.getRemoteNode(node)

  def getRemoteNode(self, node):
    """Obtains a Remote object for a node, caching the object"""
    from remote import Remote
    if (not self.mcvirt_instance.remote_nodes.has_key(node)):
      self.mcvirt_instance.remote_nodes[node] = Remote(self, node)
    return self.mcvirt_instance.remote_nodes[node]

  def getClusterConfig(self):
    """Gets the McVirt cluster configuration"""
    return McVirtConfig().getConfig()['cluster']

  def getNodeConfig(self, node):
    """Returns the configuration for a node"""
    self.ensureNodeExists(node)
    return self.getClusterConfig()['nodes'][node]

  def getNodes(self):
    """Returns an array of node configurations"""
    cluster_config = self.getClusterConfig()
    return cluster_config['nodes'].keys()

  def runRemoteCommand(self, action, arguments):
    return_data = {}
    for node in self.getNodes():
      node_object = self.getRemoteNode(node)
      return_data[node] = node_object.runRemoteCommand(action, arguments)
    return return_data

  def checkNodeExists(self, node_name):
    """Determines if a node is already present in the cluster"""
    return (node_name in self.getNodes())

  def ensureNodeExists(self, node):
    """Checks if node exists and throws exception if it does not"""
    if (not self.checkNodeExists(node)):
      raise NodeDoesNotExistException('Node %s does not exist' % node)

  def addNodeConfiguration(self, node_name, ip_address, public_key):
    """Adds McVirt node to configuration and generates SSH
    authorized_keys file"""
    # Add node to configuration file
    def addNode(mcvirt_config):
      mcvirt_config['cluster']['nodes'][node_name] = {
        'ip_address': ip_address,
        'public_key': public_key
      }
    McVirtConfig().updateConfig(addNode)
    self.buildAuthorizedKeysFile()

  def removeNodeConfiguration(self, node_name):
    """Removes an McVirt node from the configuration and regenerates
    authorized_keys file"""
    def removeNodeConfig(mcvirt_config):
      del(mcvirt_config['cluster']['nodes'][node_name])
    McVirtConfig().updateConfig(removeNodeConfig)
    self.buildAuthorizedKeysFile()

  def buildAuthorizedKeysFile(self):
    """Generates the authorized_keys file using the public keys
    from the McVirt cluster node configuration"""
    with open(self.SSH_AUTHORIZED_KEYS_FILE, 'w') as text_file:
      text_file.write("# Generated by McVirt\n")
      nodes = self.getNodes()
      for node_name in nodes:
        node_config = self.getNodeConfig(node_name)
        text_file.write("%s\n" % node_config['public_key'])

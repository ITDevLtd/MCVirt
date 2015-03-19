#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import os.path
from mcvirt.auth import Auth
from mcvirt.mcvirt import McVirtException
import json
import socket

class NodeAlreadyPresent(McVirtException):
  """Node being added is already connected to cluster"""
  pass

class NodeDoesNotExistException(McVirtException):
  """The node does not exist"""
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

  def __init__(self, mcvirt_instance, initialise_nodes=True):
    """Sets member variables"""
    self.mcvirt_instance = mcvirt_instance
    self.remote_objects = {}

    # Connect to each of the nodes
    if (initialise_nodes):
      self.connectNodes()

  def tearDown(self):
    """Disconnect from each node and removes the reference to the McVirt instance"""
    # Disconnect from each of the nodes
    for connection in self.remote_objects:
      self.remote_objects[connection] = None
    # Remove the McVirt instance, so that garbage collection
    # works correctly
    self.mcvirt_instance = None

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

    local_public_key = self.getSshPublicKey()
    remote_public_key = self.configureRemoteMachine(remote_host, remote_ip, password, local_public_key)
    self.addNodeConfiguration(remote_host, remote_ip, remote_public_key)

    # Connect to remote machine ensuring that it saves the host file
    remote = Remote(self, remote_host)
    remote.runRemoteCommand('cluster-cluster-addHostKey', {'node': self.getHostname()})

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
      self.mcvirt_instance.runCommand(('/usr/bin/ssh-keygen', '-t', 'rsa', '-N', '', '-q', '-f', Cluster.SSH_PRIVATE_KEY))

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
    if (not self.remote_objects.has_key(node)):
      self.remote_objects[node] = Remote(self, node)
    return self.remote_objects[node]

  def getClusterConfig(self):
    """Gets the McVirt cluster configuration"""
    return self.mcvirt_instance.getConfigObject().getConfig()['cluster']

  def getNodeConfig(self, node):
    """Returns the configuration for a node"""
    self.ensureNodeExists(node)
    return self.getClusterConfig()['nodes'][node]

  def getNodes(self):
    """Returns an array of node configurations"""
    cluster_config = self.getClusterConfig()
    return cluster_config['nodes'].keys()

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
    self.mcvirt_instance.getConfigObject().updateConfig(addNode)
    self.buildAuthorizedKeysFile()

  def removeNodeConfiguration(self, node_name):
    """Removes an McVirt node from the configuration and regenerates
    authorized_keys file"""
    def removeNodeConfig(mcvirt_config):
      del(mcvirt_config['cluster']['nodes'][node_name])
    self.mcvirt_instance.getConfigObject().updateConfig(removeNodeConfig)
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

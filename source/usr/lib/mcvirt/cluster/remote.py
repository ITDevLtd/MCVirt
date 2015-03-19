#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import AuthenticationException

from mcvirt.mcvirt import McVirtException

class RemoteCommandExecutionFailedException(McVirtException):
  """A remote command execution fails"""
  pass

class UnkownRemoteCommandException(McVirtException):
  """An unknown command was passed to the remote machine"""
  pass

class NodeAuthenticationException(McVirtException):
  """Incorrect password supplied for remote node"""
  pass

class CouldNotConnectToNodeException(McVirtException):
  """Could not connect to remove cluster node"""
  pass

class Remote:
  """A class to perform remote commands on McVirt nodes"""

  REMOTE_MCVIRT_COMMAND = '/usr/lib/mcvirt/mcvirt-remote.py'

  @staticmethod
  def receiveRemoteCommand(mcvirt_instance, data):
    from cluster import Cluster
    """Handles incoming data from the remote host"""
    received_data = json.loads(data)
    command = received_data['command']
    arguments = received_data['arguments']

    return_data = []
    end_connection = False

    if (command == 'cluster-cluster-addNodeRemote'):
      # Adds a remote node to the local cluster configuration
      return_data = mcvirt_instance.getClusterObject().addNodeRemote(arguments['node'], arguments['ip_address'], arguments['public_key'])
    elif (command == 'cluster-cluster-addHostKey'):
      # Connect to the remote machine, saving the host key
      remote = Remote(mcvirt_instance.getClusterObject(), arguments['node'], save_hostkey=True, initialise_node=False)
      remote = None
    elif (command == 'cluster-cluster-removeNodeConfiguration'):
      # Removes a remove McVirt node from the local configuration
      mcvirt_instance.getClusterObject().removeNodeConfiguration(arguments['node'])
    elif (command == 'close'):
      # Delete McVirt instance, which removes the lock and force mcvirt-remote
      # to close
      mcvirt_instance = None
      end_connection = True
    elif (command == 'checkStatus'):
      return_data = '1'
    else:
      raise UnkownRemoteCommandException('Unknown command: %s' % command)

    return (json.dumps(return_data), end_connection)

  def __init__(self, cluster_instance, name, save_hostkey=False, initialise_node=True, remote_ip=None, password=None):
    """Sets member variables"""
    self.name = name
    self.connection = None
    self.password = password
    self.save_hostkey = save_hostkey
    self.cluster_instance = cluster_instance
    self.initialise_node = initialise_node

    # Ensure the node exists
    if (not self.save_hostkey):
      self.cluster_instance.ensureNodeExists(self.name)

    # If the user has not specified a remote IP address, get it from the node configuration
    if (remote_ip):
      self.remote_ip = remote_ip
    else:
      self.remote_ip = self.cluster_instance.getNodeConfig(name)['ip_address']

    self.__connect()

  def __del__(self):
    """Stop the SSH connection when the object is deleted"""
    if (self.connection):
      # Save the known_hosts file if specified
      if (self.save_hostkey):
        self.connection.save_host_keys(self.cluster_instance.SSH_KNOWN_HOSTS_FILE)

      if (self.initialise_node):
        # Tell remote script to close
        self.runRemoteCommand('close', None)

      # Close the SSH connection
      self.connection.close()

  def __connect(self):
    """Connect the SSH session"""
    if (self.connection is None):
      ssh_client = SSHClient()

      # Loads the user's known hosts file
      ssh_client.load_host_keys(self.cluster_instance.SSH_KNOWN_HOSTS_FILE)

      # If the hostkey is to be saved, allow unknown hosts
      if (self.save_hostkey):
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())

      # Attempt to connect to the host
      try:
        if (self.password is not None):
          ssh_client.connect(self.remote_ip, username=self.cluster_instance.SSH_USER, password=self.password, timeout=10)
        else:
          ssh_client.connect(self.remote_ip, username=self.cluster_instance.SSH_USER, key_filename=self.cluster_instance.SSH_PRIVATE_KEY, timeout=10)
      except AuthenticationException:
        raise NodeAuthenticationException('Could not authenticate to node: %s' % self.name)
      except Exception, e:
        raise CouldNotConnectToNodeException('Could not connect to node: %s' % self.name)

      # Save the SSH client object
      self.connection = ssh_client

      if (self.initialise_node):
        # Run McVirt command
        (self.stdin, self.stdout, self.stderr) = self.connection.exec_command(self.REMOTE_MCVIRT_COMMAND)

        # Check the remote lock
        if (self.runRemoteCommand('checkStatus', None) != '1'):
          raise McVirtException('Remote node locked: %s' % self.name)

  def runRemoteCommand(self, command, arguments):
    """Prepare and run a remote command on a cluster node"""
    # Generate a JSON of the command and arguments
    command_json = json.dumps({'command': command, 'arguments': arguments}, sort_keys=True)

    # Perform the remote command
    self.stdin.write("%s\n" % command_json)
    self.stdin.flush()
    stdout = self.stdout.readline()

    # Attempt to convert stdout to JSON
    try:
      # Obtains the first line of output and decode JSON
      return json.loads(str.strip(stdout))
    except ValueError, e:
    # If the exit code was not 0, close the SSH session and throw an exception
      stderr = self.stderr.readlines()
      if (stderr):
        exit_code = self.stdout.channel.recv_exit_status()
        self.connection.close()
        raise RemoteCommandExecutionFailedException("Exit Code: %s\nCommand: %s\nStdout: %s\nStderr: %s" % (exit_code, command_json, ''.join(stdout), ''.join(stderr)))

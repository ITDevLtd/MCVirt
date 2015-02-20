#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import AuthenticationException
from mcvirt.mcvirt import McVirt, McVirtException
from cluster import Cluster

class RemoteCommandExecutionFailedException(McVirtException):
  """A remote command execution fails"""
  pass

class UnkownRemoteCommandException(McVirtException):
  """An unknown command was passed to the remote machine"""
  pass

class NodeAuthenticationException(McVirtException):
  """Incorrect password supplied for remote node"""
  pass

class Remote:
  """A class to perform remote commands on McVirt nodes"""

  REMOTE_MCVIRT_COMMAND = '/usr/lib/mcvirt/mcvirt-remote.py'

  @staticmethod
  def receiveRemoteCommand(mcvirt_instance, data):
    """Handles incoming data from the remote host"""
    received_data = json.loads(data)
    command = received_data['command']
    arguments = received_data['arguments']

    return_data = None

    if (command == 'cluster-cluster-addNodeRemote'):
      # Adds a remote node to the local cluster configuration
      cluster_instance = Cluster(mcvirt_instance)
      return_data = cluster_instance.addNodeRemote(arguments['node'], arguments['ip_address'], arguments['public_key'])
    elif (command == 'cluster-cluster-addHostKey'):
      # Connect to the remote machine, saving the host key
      cluster_instance = Cluster(mcvirt_instance)
      remote = Remote(cluster_instance, arguments['node'], True)
      remote.__connect()
      remote = None
    elif (command == 'cluster-cluster-removeNodeConfiguration'):
      # Removes a remove McVirt node from the local configuration
      cluster_instance = Cluster(mcvirt_instance)
      cluster_instance.removeNodeConfiguration(arguments['node'])
    else:
      raise UnkownRemoteCommandException('Unknown command: %s' % command)

    if (return_data is not None):
      return json.dumps(return_data)

  def __init__(self, cluster_object, name, save_hostkey=False, remote_ip=None, password=None):
    """Sets member variables"""
    self.name = name
    self.connection = None
    self.password = password
    self.save_hostkey = save_hostkey
    self.cluster_instance = cluster_object

    # If the user has not specified a remote IP address, get it from the node configuration
    if (remote_ip):
      self.remote_ip = remote_ip
    else:
      self.remote_ip = self.cluster_instance.getNodeConfig(name)['ip_address']

  def __delete__(self):
    """Stop the SSH connection when the object is deleted"""
    # Save the known_hosts file if specified
    if (self.save_hostkey):
      self.connection.save_host_keys(Cluster.SSH_KNOWN_HOSTS_FILE)

    # Close the SSH connection
    self.connection.close()

  def __connect(self):
    """Connect the SSH session"""
    if (self.connection is None):
      ssh_client = SSHClient()

      # Loads the user's known hosts file
      ssh_client.load_host_keys(Cluster.SSH_KNOWN_HOSTS_FILE)

      # If the hostkey is to be saved, allow unknown hosts
      if (self.save_hostkey):
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())

      # Attempt to connect to the host
      try:
        if (self.password is not None):
          ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER, password=self.password)
        else:
          ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER, key_filename=Cluster.SSH_PRIVATE_KEY)
      except AuthenticationException:
        raise NodeAuthenticationException('Incorrect password for %s' % self.remote)

      # Save the SSH client object
      self.connection = ssh_client

  def runRemoteCommand(self, command, arguments):
    """Prepare and run a remote command on a cluster node"""
    # Ensure SSH is connected
    self.__connect()

    # Generate a JSON of the command and arguments
    command_json = json.dumps({'command': command, 'arguments': arguments}, sort_keys=True)

    # Escape quotes in command
    command_json = command_json.replace(r"'", r"'\''")

    # Perform the remote command and capture stdout and stderr
    stdin, stdout, stderr = self.connection.exec_command('%s \'%s\'' % (self.REMOTE_MCVIRT_COMMAND, command_json))
    exit_code = stdout.channel.recv_exit_status()
    stdout = stdout.readlines()
    stderr = stderr.readlines()

    # If the exit code was not 0, close the SSH session and throw an exception
    if (exit_code):
      self.connection.close()
      raise RemoteCommandExecutionFailedException("Exit Code: %s\nCommand: %s\nStdout: %s\nStderr: %s" % (exit_code, command_json, ''.join(stdout), ''.join(stderr)))

    # Obtains the first line of output and decode JSON
    if (len(stdout)):
      json_data = json.loads(str.strip(stdout[0]))
    else:
      json_data = []
    return json_data

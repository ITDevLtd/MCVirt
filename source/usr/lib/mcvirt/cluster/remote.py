#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import json
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import AuthenticationException

from mcvirt.mcvirt import McVirtException
from cluster import Cluster
from mcvirt.auth import Auth

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
    """Handles incoming data from the remote host"""
    from cluster import Cluster
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    received_data = json.loads(data)
    action = received_data['action']
    arguments = received_data['arguments']

    return_data = []
    end_connection = False

    if (action == 'cluster-cluster-addNodeRemote'):
      # Adds a remote node to the local cluster configuration
      cluster_instance = Cluster(mcvirt_instance)
      return_data = cluster_instance.addNodeRemote(arguments['node'], arguments['ip_address'], arguments['public_key'])
    elif (action == 'cluster-cluster-addHostKey'):
      # Connect to the remote machine, saving the host key
      cluster_instance = Cluster(mcvirt_instance)
      remote = Remote(cluster_instance, arguments['node'], save_hostkey=True, initialise_node=False)
      remote = None
    elif (action == 'cluster-cluster-removeNodeConfiguration'):
      # Removes a remove McVirt node from the local configuration
      cluster_instance = Cluster(mcvirt_instance)
      cluster_instance.removeNodeConfiguration(arguments['node'])
    elif (action == 'auth-addUserPermissionGroup'):
      auth_object = mcvirt_instance.getAuthObject()
      vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
      auth_object.addUserPermissionGroup(mcvirt_object=mcvirt_instance, vm_object=vm_object,
                                         permission_group=arguments['permission_group'],
                                         username=arguments['username'])
    elif (action == 'auth-deleteUserPermissionGroup'):
      auth_object = mcvirt_instance.getAuthObject()
      vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
      auth_object.deleteUserPermissionGroup(mcvirt_object=mcvirt_instance, vm_object=vm_object,
                                            permission_group=arguments['permission_group'],
                                            username=arguments['username'])
    elif (action == 'close'):
      # Delete McVirt instance, which removes the lock and force mcvirt-remote
      # to close
      end_connection = True
    elif (action == 'checkStatus'):
      return_data = ['0']
    else:
      raise UnkownRemoteCommandException('Unknown command: %s' % command)

    return (json.dumps(return_data), end_connection)

  def __init__(self, cluster_instance, name, save_hostkey=False, initialise_node=True, remote_ip=None, password=None):
    """Sets member variables"""
    self.name = name
    self.connection = None
    self.password = password
    self.save_hostkey = save_hostkey
    self.initialise_node = initialise_node

    # Ensure the node exists
    if (not self.save_hostkey):
      cluster_instance.ensureNodeExists(self.name)

    # If the user has not specified a remote IP address, get it from the node configuration
    if (remote_ip):
      self.remote_ip = remote_ip
    else:
      self.remote_ip = cluster_instance.getNodeConfig(name)['ip_address']

    self.__connect()

  def __del__(self):
    """Stop the SSH connection when the object is deleted"""
    if (self.connection):
      # Save the known_hosts file if specified
      if (self.save_hostkey):
        self.connection.save_host_keys(Cluster.SSH_KNOWN_HOSTS_FILE)

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
      ssh_client.load_host_keys(Cluster.SSH_KNOWN_HOSTS_FILE)

      # If the hostkey is to be saved, allow unknown hosts
      if (self.save_hostkey):
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())

      # Attempt to connect to the host
      try:
        if (self.password is not None):
          ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER, password=self.password, timeout=10)
        else:
          ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER, key_filename=Cluster.SSH_PRIVATE_KEY, timeout=10)
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
        if (self.runRemoteCommand('checkStatus', None) != ['0']):
          raise McVirtException('Remote node locked: %s' % self.name)

  def runRemoteCommand(self, action, arguments):
    """Prepare and run a remote command on a cluster node"""
    # Generate a JSON of the command and arguments
    command_json = json.dumps({'action': action, 'arguments': arguments}, sort_keys=True)

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

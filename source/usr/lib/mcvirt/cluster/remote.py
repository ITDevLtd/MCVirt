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
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import AuthenticationException

from mcvirt.mcvirt import MCVirtException
from cluster import Cluster


class RemoteCommandExecutionFailedException(MCVirtException):
    """A remote command execution fails"""
    pass


class UnknownRemoteCommandException(MCVirtException):
    """An unknown command was passed to the remote machine"""
    pass


class NodeAuthenticationException(MCVirtException):
    """Incorrect password supplied for remote node"""
    pass


class CouldNotConnectToNodeException(MCVirtException):
    """Could not connect to remove cluster node"""
    pass


class Remote:
    """A class to perform remote commands on MCVirt nodes"""

    REMOTE_MCVIRT_COMMAND = '/usr/lib/mcvirt/mcvirt-remote.py'

    @staticmethod
    def receiveRemoteCommand(mcvirt_instance, data):
        """Handles incoming data from the remote host"""
        from mcvirt.virtual_machine.virtual_machine import VirtualMachine
        received_data = json.loads(data)
        action = received_data['action']
        arguments = received_data['arguments']

        return_data = []
        end_connection = False

        if (action == 'cluster-cluster-addNodeRemote'):
            # Adds a remote node to the local cluster configuration
            cluster_instance = Cluster(mcvirt_instance)
            return_data = cluster_instance.addNodeRemote(arguments['node'],
                                                         arguments['ip_address'],
                                                         arguments['public_key'])

        elif (action == 'cluster-cluster-addHostKey'):
            # Connect to the remote machine, saving the host key
            cluster_instance = Cluster(mcvirt_instance)
            Remote(cluster_instance, arguments['node'],
                   save_hostkey=True, initialise_node=False)

        elif (action == 'cluster-cluster-removeNodeConfiguration'):
            # Removes a remove MCVirt node from the local configuration
            cluster_instance = Cluster(mcvirt_instance)
            cluster_instance.removeNodeConfiguration(arguments['node'])

        elif (action == 'auth-addUserPermissionGroup'):
            auth_object = mcvirt_instance.getAuthObject()
            if ('vm_name' in arguments and arguments['vm_name']):
                vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            else:
                vm_object = None

            if ('ignore_duplicate' in arguments and arguments['ignore_duplicate']):
                ignore_duplicate = arguments['ignore_duplicate']
            else:
                ignore_duplicate = False

            auth_object.addUserPermissionGroup(mcvirt_object=mcvirt_instance,
                                               permission_group=arguments['permission_group'],
                                               username=arguments['username'],
                                               vm_object=vm_object,
                                               ignore_duplicate=ignore_duplicate)

        elif (action == 'auth-deleteUserPermissionGroup'):
            auth_object = mcvirt_instance.getAuthObject()
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            auth_object.deleteUserPermissionGroup(mcvirt_object=mcvirt_instance,
                                                  permission_group=arguments['permission_group'],
                                                  username=arguments['username'],
                                                  vm_object=vm_object)

        elif (action == 'auth-addSuperuser'):
            auth_object = mcvirt_instance.getAuthObject()
            if ('ignore_duplicate' in arguments and arguments['ignore_duplicate']):
                ignore_duplicate = arguments['ignore_duplicate']
            else:
                ignore_duplicate = False
            auth_object.addSuperuser(arguments['username'],
                                     ignore_duplicate=ignore_duplicate)

        elif (action == 'virtual_machine-getAllVms'):
            return_data = VirtualMachine.getAllVms(mcvirt_instance, Cluster.getHostname())

        elif (action == 'virtual_machine-create'):
            VirtualMachine.create(mcvirt_instance, arguments['vm_name'], arguments['cpu_cores'],
                                  arguments['memory_allocation'], node=arguments['node'],
                                  available_nodes=arguments['available_nodes'])

        elif (action == 'virtual_machine-delete'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.delete(remove_data=arguments['remove_data'])

        elif (action == 'virtual_machine-register'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.register(set_node=False)

        elif (action == 'virtual_machine-unregister'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.unregister()

        elif (action == 'virtual_machine-start'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.start()

        elif (action == 'virtual_machine-stop'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.stop()

        elif (action == 'network_adapter-create'):
            from mcvirt.node.network import Network
            from mcvirt.virtual_machine.network_adapter import NetworkAdapter
            network_object = Network(mcvirt_instance, arguments['network_name'])
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            NetworkAdapter.create(vm_object, network_object, arguments['mac_address'])

        elif (action == 'virtual_machine-getState'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            return_data = vm_object.getState().value

        elif (action == 'virtual_machine-getInfo'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            return_data = vm_object.getInfo()

        elif (action == 'virtual_machine-getAllVms'):
            return_data = VirtualMachine.getAllVms(mcvirt_instance)

        elif (action == 'virtual_machine-setNode'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object._setNode(arguments['node'])

        elif (action == 'virtual_machine-virtual_machine-updateConfig'):
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            vm_object.updateConfig(attribute_path=arguments['attribute_path'],
                                   value=arguments['value'],
                                   reason=arguments['reason'])

        elif (action == 'virtual_machine-hard_drive-createLogicalVolume'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._createLogicalVolume(hard_drive_config_object,
                                                  name=arguments['name'],
                                                  size=arguments['size'])

        elif (action == 'virtual_machine-hard_drive-removeLogicalVolume'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            ignore_non_existent = arguments['ignore_non_existent']
            hard_drive_class._removeLogicalVolume(hard_drive_config_object,
                                                  name=arguments['name'],
                                                  ignore_non_existent=ignore_non_existent)

        elif (action == 'virtual_machine-hard_drive-activateLogicalVolume'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._activateLogicalVolume(hard_drive_config_object,
                                                    name=arguments['name'])

        elif (action == 'virtual_machine-hard_drive-zeroLogicalVolume'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._zeroLogicalVolume(hard_drive_config_object,
                                                name=arguments['name'],
                                                size=arguments['size'])

        elif (action == 'virtual_machine-hard_drive-drbd-generateDrbdConfig'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_config_object._generateDrbdConfig()

        elif (action == 'virtual_machine-hard_drive-drbd-removeDrbdConfig'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_config_object._removeDrbdConfig()

        elif (action == 'virtual_machine-hard_drive-drbd-initialiseMetaData'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._initialiseMetaData(hard_drive_config_object._getResourceName())

        elif (action == 'virtual_machine-hard_drive-addToVirtualMachine'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._addToVirtualMachine(hard_drive_config_object)

        elif (action == 'virtual_machine-hard_drive-removeFromVirtualMachine'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._removeFromVirtualMachine(hard_drive_config_object)

        elif (action == 'virtual_machine-hard_drive-drbd-drbdUp'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._drbdUp(hard_drive_config_object)

        elif (action == 'virtual_machine-hard_drive-drbd-drbdDown'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            hard_drive_config_object = HardDriveFactory.getRemoteConfigObject(mcvirt_instance,
                                                                              arguments['config'])
            hard_drive_class = HardDriveFactory.getClass(hard_drive_config_object._getType())
            hard_drive_class._drbdDown(hard_drive_config_object)

        elif (action == 'virtual_machine-hard_drive-drbd-drbdSetPrimary'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])

            if ('allow_two_primaries' in arguments):
                allow_two_primaries = arguments['allow_two_primaries']
            else:
                allow_two_primaries = False

            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object._drbdSetPrimary(allow_two_primaries=allow_two_primaries)

        elif (action == 'virtual_machine-hard_drive-drbd-drbdSetSecondary'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object._drbdSetSecondary()

        elif (action == 'virtual_machine-hard_drive-drbd-setTwoPrimariesConfig'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object._setTwoPrimariesConfig(arguments['allow'])

        elif (action == 'virtual_machine-hard_drive-drbd-drbdConnect'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object._drbdConnect()

        elif (action == 'virtual_machine-hard_drive-drbd-drbdDisconnect'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object._drbdDisconnect()

        elif (action == 'node-network-create'):
            from mcvirt.node.network import Network
            Network.create(mcvirt_instance,
                           arguments['network_name'],
                           arguments['physical_interface'])

        elif (action == 'node-network-delete'):
            from mcvirt.node.network import Network
            network_object = Network(mcvirt_instance, arguments['network_name'])
            network_object.delete()

        elif (action == 'node-network-checkExists'):
            from mcvirt.node.network import Network
            return_data = Network._checkExists(arguments['network_name'])

        elif (action == 'node-network-getConfig'):
            from mcvirt.node.network import Network
            return_data = Network.getConfig()

        elif (action == 'node-drbd-isInstalled'):
            from mcvirt.node.drbd import DRBD
            return_data = DRBD.isInstalled()

        elif (action == 'node-drbd-isEnabled'):
            from mcvirt.node.drbd import DRBD
            return_data = DRBD.isEnabled()

        elif (action == 'node-drbd-enable'):
            from mcvirt.node.drbd import DRBD
            DRBD.enable(mcvirt_instance, arguments['secret'])

        elif (action == 'virtual_machine-hard_drive-drbd-setSyncState'):
            from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
            vm_object = VirtualMachine(mcvirt_instance, arguments['vm_name'])
            hard_drive_object = HardDriveFactory.getObject(vm_object, arguments['disk_id'])
            hard_drive_object.setSyncState(arguments['sync_state'])

        elif (action == 'iso-getIsos'):
            from mcvirt.iso import Iso
            return_data = Iso.getIsos(mcvirt_instance)

        elif (action == 'mcvirt-obtainLock'):
            timeout = arguments['timeout']
            mcvirt_instance.obtainLock(timeout)

        elif (action == 'mcvirt-releaseLock'):
            mcvirt_instance.releaseLock()

        elif (action == 'close'):
            # Delete MCVirt instance, which removes the lock and force mcvirt-remote
            # to close
            end_connection = True

        elif (action == 'checkStatus'):
            return_data = ['0']

        else:
            raise UnknownRemoteCommandException('Unknown command: %s' % action)

        return (json.dumps(return_data), end_connection)

    def __init__(self, cluster_instance, name,
                 save_hostkey=False, initialise_node=True,
                 remote_ip=None, password=None):
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
                    ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER,
                                       password=self.password, timeout=10)
                else:
                    ssh_client.connect(self.remote_ip, username=Cluster.SSH_USER,
                                       key_filename=Cluster.SSH_PRIVATE_KEY,
                                       timeout=10)
            except AuthenticationException:
                raise NodeAuthenticationException('Could not authenticate to node: %s' % self.name)
            except Exception:
                from mcvirt.auth import Auth

                if (Auth().checkPermission(Auth.PERMISSIONS.CAN_IGNORE_CLUSTER)):
                    ignore_node_message = "\nThe cluster can be ignored using --ignore-failed-nodes"
                else:
                    ignore_node_message = ''
                raise CouldNotConnectToNodeException('Could not connect to node: %s' % self.name +
                                                     ignore_node_message)

            # Save the SSH client object
            self.connection = ssh_client

            if (self.initialise_node):
                # Run MCVirt command
                (self.stdin,
                 self.stdout,
                 self.stderr) = self.connection.exec_command(self.REMOTE_MCVIRT_COMMAND)

                # Check the remote lock
                if (self.runRemoteCommand('checkStatus', None) != ['0']):
                    raise MCVirtException('Remote node locked: %s' % self.name)

    def runRemoteCommand(self, action, arguments):
        """Prepare and run a remote command on a cluster node"""
        # Ensure connection is alive
        if (self.connection is None):
            self.__connect()

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
        except ValueError:
            # If the exit code was not 0, close the SSH session and throw an exception
            stderr = self.stderr.readlines()
            if (stderr):
                exit_code = self.stdout.channel.recv_exit_status()
                self.connection.close()
                self.connection = None
                raise RemoteCommandExecutionFailedException(
                    "Exit Code: %s\nNode: %s\nCommand: %s\nStdout: %s\nStderr: %s" %
                    (exit_code, self.name, command_json, ''.join(stdout), ''.join(stderr))
                )

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

from enum import Enum
import os
import Pyro4

from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.drbd import DRBD as ConfigDRBD
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode, DRBDSocket
from mcvirt.auth.auth import Auth
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.system import System
from mcvirt.cluster.cluster import Cluster
from mcvirt.rpc.lock import lockingMethod
from mcvirt.mcvirt import MCVirt
from mcvirt.exceptions import (DrbdStateException, DrbdBlockDeviceDoesNotExistException,
                               DrbdVolumeNotInSyncException, MCVirtCommandException)


class DrbdConnectionState(Enum):
    """Library of DRBD connection states"""

    # No network configuration available. The resource has not yet been connected,
    # or has been administratively disconnected (using drbdadm disconnect), or has
    # dropped its connection due to failed authentication or split brain.
    STAND_ALONE = 'StandAlone'
    # Temporary state during disconnection. The next state is StandAlone.
    DISCONNECTING = 'Disconnecting'
    # Temporary state, prior to a connection attempt. Possible next
    # states: WFConnection and WFReportParams.
    UNCONNECTED = 'Unconnected'
    # Temporary state following a timeout in the communication with the peer.
    # Next state: Unconnected.
    TIMEOUT = 'Timeout'
    # Temporary state after the connection to the peer was lost.
    # Next state: Unconnected.
    BROKEN_PIPE = 'BrokenPipe'
    # Temporary state after the connection to the partner was lost.
    # Next state: Unconnected.
    NETWORK_FAILURE = 'NetworkFailure'
    # Temporary state after the connection to the partner was lost.
    # Next state: Unconnected.
    PROTOCOL_ERROR = 'ProtocolError'
    # Temporary state. The peer is closing the connection. Next state: Unconnected.
    TEAR_DOWN = 'TearDown'
    # This node is waiting until the peer node becomes visible on the network.
    WF_CONNECTION = 'WFConnection'
    # TCP connection has been established, this node waits for the first
    # network packet from the peer.
    WF_REPORT_PARAMS = 'WFReportParams'
    # A DRBD connection has been established, data mirroring is now active.
    # This is the normal state.
    CONNECTED = 'Connected'
    # Full synchronization, initiated by the administrator, is just starting.
    # The next possible states are: SyncSource or PausedSyncS.
    STARTING_SYNC_S = 'StartingSyncS'
    # Full synchronization, initiated by the administrator, is just starting.
    # Next state: WFSyncUUID.
    STARTING_SYNC_T = 'StartingSyncT'
    # Partial synchronization is just starting. Next possible states:
    # SyncSource or PausedSyncS.
    WF_BIT_MAP_S = 'WFBitMapS'
    # Partial synchronization is just starting. Next possible state: WFSyncUUID.
    WF_BIT_MAP_T = 'WFBitMapT'
    # Synchronization is about to begin. Next possible states: SyncTarget or PausedSyncT.
    WF_SYNC_UUID = 'WFSyncUUID'
    # Synchronization is currently running, with the local node being the
    # source of synchronization.
    SYNC_SOURCE = 'SyncSource'
    # Synchronization is currently running, with the local node being the
    # target of synchronization.
    SYNC_TARGET = 'SyncTarget'
    # The local node is the source of an ongoing synchronization,
    # but synchronization is currently paused.
    # This may be due to a dependency on the completion of another synchronization process,
    # or due to synchronization having been manually interrupted by drbdadm pause-sync.
    PAUSED_SYNC_S = 'PausedSyncS'
    # The local node is the target of an ongoing synchronization,
    # but synchronization is currently paused.
    # This may be due to a dependency on the completion of another synchronization process,
    # or due to synchronization having been manually interrupted by drbdadm pause-sync.
    PAUSED_SYNC_T = 'PausedSyncT'
    # On-line device verification is currently running, with the local node
    # being the source of verification.
    VERIFY_S = 'VerifyS'
    # On-line device verification is currently running, with the local node
    # being the target of verification.
    VERIFY_T = 'VerifyT'


class DrbdRoleState(Enum):
    """Library of DRBD role states"""

    # The resource is currently in the primary role, and may be read from and written to.
    # This role only occurs on one of the two nodes, unless dual-primary mode is enabled.
    PRIMARY = 'Primary'
    # The resource is currently in the secondary role. It normally receives updates from its peer
    # (unless running in disconnected mode), but may neither be read from nor written to.
    # This role may occur on one or both nodes.
    SECONDARY = 'Secondary'
    # The resource's role is currently unknown. The local resource role never has this status.
    # It is only displayed for the peer's resource role, and only in disconnected mode.
    UNKNOWN = 'Unknown'


class DrbdDiskState(Enum):
    """Library of DRBD disk states"""

    # No local block device has been assigned to the DRBD driver. This may mean that the resource
    # has never attached to its backing device, that it has been manually detached using
    # drbdadm detach, or that it automatically detached after a lower-level I/O error.
    DISKLESS = 'Diskless'
    # Transient state while reading meta data.
    ATTACHING = 'Attaching'
    # Transient state following an I/O failure report by the local block
    # device. Next state: Diskless.
    FAILED = 'Failed'
    # Transient state when an Attach is carried out on an already-Connected DRBD device.
    NEGOTIATING = 'Negotiating'
    # The data is inconsistent. This status occurs immediately upon creation of a new resource,
    # on both nodes (before the initial full sync). Also, this status is found in one node
    # (the synchronization target) during synchronization.
    INCONSISTENT = 'Inconsistent'
    # Resource data is consistent, but outdated.
    OUTDATED = 'Outdated'
    # This state is used for the peer disk if no network connection is available.
    D_UNKNOWN = 'DUnknown'
    # Consistent data of a node without connection. When the connection is established,
    # it is decided whether the data is UpToDate or Outdated.
    CONSISTENT = 'Consistent'
    # Consistent, up-to-date state of the data. This is the normal state.
    UP_TO_DATE = 'UpToDate'


class DRBD(Base):
    """Provides operations to manage DRBD-backed hard drives, used by VMs"""

    CREATE_PROGRESS = Enum('CREATE_PROGRESS',
                           ['START',
                            'CREATE_RAW_LV',
                            'CREATE_META_LV',
                            'CREATE_DRBD_CONFIG',
                            'CREATE_DRBD_CONFIG_R',
                            'DRBD_UP',
                            'DRBD_UP_R',
                            'ADD_TO_VM',
                            'DRBD_CONNECT',
                            'DRBD_CONNECT_R'])

    DRBD_STATES = {
        'CONNECTION': {
            'OK': [
                DrbdConnectionState.CONNECTED,
                DrbdConnectionState.VERIFY_S,
                DrbdConnectionState.VERIFY_T,
                DrbdConnectionState.PAUSED_SYNC_S,
                DrbdConnectionState.STARTING_SYNC_S,
                DrbdConnectionState.SYNC_SOURCE,
                DrbdConnectionState.WF_BIT_MAP_S,
                DrbdConnectionState.WF_BIT_MAP_T,
                DrbdConnectionState.WF_SYNC_UUID
            ],
            'CONNECTED': [
                DrbdConnectionState.CONNECTED,
                DrbdConnectionState.VERIFY_S,
                DrbdConnectionState.VERIFY_T,
                DrbdConnectionState.PAUSED_SYNC_S,
                DrbdConnectionState.STARTING_SYNC_S,
                DrbdConnectionState.SYNC_SOURCE,
                DrbdConnectionState.SYNC_TARGET,
                DrbdConnectionState.WF_BIT_MAP_S,
                DrbdConnectionState.WF_BIT_MAP_T,
                DrbdConnectionState.WF_SYNC_UUID
            ],
            'WARNING': [
                DrbdConnectionState.STAND_ALONE,
                DrbdConnectionState.DISCONNECTING,
                DrbdConnectionState.UNCONNECTED,
                DrbdConnectionState.BROKEN_PIPE,
                DrbdConnectionState.NETWORK_FAILURE,
                DrbdConnectionState.WF_CONNECTION,
                DrbdConnectionState.WF_REPORT_PARAMS
            ]
        },
        'ROLE': {
            'OK': [DrbdRoleState.PRIMARY],
            'WARNING': []
        },
        'DISK': {
            'OK': [DrbdDiskState.UP_TO_DATE],
            'WARNING': [DrbdDiskState.CONSISTENT, DrbdDiskState.D_UNKNOWN]
        }
    }

    INITIAL_PORT = 7789
    INITIAL_MINOR = 1
    DRBD_RAW_SUFFIX = 'raw'
    DRBD_META_SUFFIX = 'meta'
    DRBD_CONFIG_TEMPLATE = MCVirt.TEMPLATE_DIR + '/drbd_resource.conf'
    CACHE_MODE = 'none'

    def __init__(self, drbd_minor=None, drbd_port=None, *args, **kwargs):
        """Sets member variables"""
        # Get DRBDe configuration from disk configuration
        self._sync_state = False
        self._drbd_port = None
        self._drbd_minor = None
        super(DRBD, self).__init__(*args, **kwargs)

    @property
    def config_properties(self):
        """Returns the disk object config items"""
        return super(DRBD, self).config_properties + ['drbd_port', 'drbd_minor']

    @staticmethod
    def isAvailable(pyro_object):
        """Determines if DRBD is available on the node"""
        if pyro_object._get_registered_object('node_drbd').isEnabled():
            return True
        else:
            return False

    def _checkExists(self):
        """Ensures the required storage elements exist on the system"""
        raw_lv = self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)
        meta_lv = self._getLogicalVolumeName(self.DRBD_META_SUFFIX)
        self._ensureLogicalVolumeExists(raw_lv)
        self._ensureLogicalVolumeExists(meta_lv)
        return True

    def activateDisk(self):
        """Ensures that the disk is ready to be used by a VM on the local node"""
        self._ensureExists()
        raw_lv = self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)
        meta_lv = self._getLogicalVolumeName(self.DRBD_META_SUFFIX)
        self._ensureLogicalVolumeActive(raw_lv)
        self._ensureLogicalVolumeActive(meta_lv)
        self._checkDrbdStatus()

        # If the disk is not already set to primary, set it to primary
        if self._drbdGetRole()[0] is not DrbdRoleState('Primary'):
            self._drbdSetPrimary()

        self._ensureBlockDeviceExists()

    def deactivateDisk(self):
        """Marks DRBD volume as secondary"""
        self._ensureExists()
        self._drbdSetSecondary()

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensureExists()
        return self._getLogicalVolumeSize(self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX))

    def create(self, size):
        """Creates a new hard drive, attaches the disk to the VM and records the disk
        in the VM configuration"""
        # Ensure user has privileges to create a DRBD volume
        self._get_registered_object('auth').assertPermission(PERMISSIONS.MANAGE_DRBD, self.vm_object)

        # Ensure DRBD is enabled on the host
        if not self._get_registered_object('node_drbd').isEnabled():
            raise DRBDNotEnabledOnNode('DRBD is not enabled on this node')

        # Create cluster object for running on remote nodes
        cluster_instance = self._get_registered_object('cluster')

        remote_nodes = self.vm_object._getRemoteNodes()

        # Keep track of progress, so the storage stack can be torn down if something goes wrong
        progress = DRBD.CREATE_PROGRESS.START
        try:
            # Create DRBD raw logical volume
            raw_logical_volume_name = self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)
            self._createLogicalVolume(raw_logical_volume_name,
                                      size, perform_on_nodes=True)
            progress = DRBD.CREATE_PROGRESS.CREATE_RAW_LV
            self._activateLogicalVolume(raw_logical_volume_name,
                                        perform_on_nodes=True)

            # Zero raw logical volume
            self._zeroLogicalVolume(raw_logical_volume_name,
                                    size, perform_on_nodes=True)

            # Create DRBD meta logical volume
            meta_logical_volume_name = self._getLogicalVolumeName(
                self.DRBD_META_SUFFIX
            )
            meta_logical_volume_size = self._calculateMetaDataSize()
            self._createLogicalVolume(meta_logical_volume_name,
                                      meta_logical_volume_size,
                                      perform_on_nodes=True)
            progress = DRBD.CREATE_PROGRESS.CREATE_META_LV
            self._activateLogicalVolume(meta_logical_volume_name,
                                        perform_on_nodes=True)

            # Zero meta logical volume
            self._zeroLogicalVolume(meta_logical_volume_name,
                                    meta_logical_volume_size, perform_on_nodes=True)

            # Generate DRBD resource configuration
            self._generateDrbdConfig()
            progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG

            cluster = self._get_registered_object('cluster')
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                remote_disk.generateDrbdConfig()
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=remote_nodes)
            progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R

            # Setup meta data on DRBD volume
            self._initialiseMetaData()
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                remote_disk.initialiseMetaData()
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=remote_nodes)

            # Bring up DRBD resource
            self._drbdUp()
            progress = DRBD.CREATE_PROGRESS.DRBD_UP
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                remote_disk.drbdUp()
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=remote_nodes)
            progress = DRBD.CREATE_PROGRESS.DRBD_UP_R

            # Wait for 5 seconds to let DRBD initialise
            # TODO: Monitor DRBD status instead.
            import time
            time.sleep(5)

            # Add to virtual machine
            self.addToVirtualMachine()
            progress = DRBD.CREATE_PROGRESS.ADD_TO_VM

            # Overwrite data on peer
            self._drbdOverwritePeer()

            # Ensure the DRBD resource is connected
            self._drbdConnect()
            progress = DRBD.CREATE_PROGRESS.DRBD_CONNECT
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                remote_disk.drbdConnect()
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=remote_nodes)
            progress = DRBD.CREATE_PROGRESS.DRBD_CONNECT_R

            # Mark volume as primary on local node
            self._drbdSetPrimary()
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                remote_disk.drbdSetSecondary()
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=remote_nodes)

        except Exception:
            cluster = self._get_registered_object('cluster')
            # If the creation fails, tear down based on the progress of the creation
            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_CONNECT_R.value):
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.drbdDisconnect()
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=remote_nodes)

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_CONNECT.value):
                self._drbdDisconnect()

            if (progress.value >= DRBD.CREATE_PROGRESS.ADD_TO_VM.value):
                self.removeFromVirtualMachine()

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_UP_R.value):
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.drbdDown()
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=remote_nodes)

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_UP.value):
                self._drbdDown()

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R.value):
                def remoteCommand(node):
                    remote_disk = self.getRemoteObject(remote_node=node, registered=False)
                    remote_disk.removeDrbdConfig()
                cluster.runRemoteCommand(callback_method=remoteCommand,
                                         nodes=remote_nodes)

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG.value):
                self._removeDrbdConfig()

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_META_LV.value):
                self._removeLogicalVolume(meta_logical_volume_name,
                                          perform_on_nodes=True)

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_RAW_LV.value):
                self._removeLogicalVolume(raw_logical_volume_name,
                                          perform_on_nodes=True)

            raise

    def _removeStorage(self):
        """Removes the backing storage for the DRBD hard drive"""
        self._ensureExists()
        cluster = self._get_registered_object('cluster')
        remote_nodes = self.vm_object._getRemoteNodes()

        # Disconnect and perform a 'down' on the DRBD volume on all nodes
        def remoteCommand(node):
            remote_disk = self.getRemoteObject(remote_node=node, registered=False)
            remote_disk.drbdDisconnect()
        cluster.runRemoteCommand(callback_method=remoteCommand,
                                 nodes=remote_nodes)
        self._drbdDisconnect()
        def remoteCommand(node):
            remote_disk = self.getRemoteObject(remote_node=node, registered=False)
            remote_disk.drbdDown()
        cluster.runRemoteCommand(callback_method=remoteCommand,
                                 nodes=remote_nodes)
        self._drbdDown()

        # Remove the DRBD configuration from all nodes
        def remoteCommand(node):
            remote_disk = self.getRemoteObject(remote_node=node, registered=False)
            remote_disk.removeDrbdConfig()
        cluster.runRemoteCommand(callback_method=remoteCommand,
                                 nodes=remote_nodes)
        self._removeDrbdConfig()

        # Remove the meta and raw logical volume from all nodes
        self._removeLogicalVolume(self._getLogicalVolumeName(self.DRBD_META_SUFFIX),
                                  perform_on_nodes=True)
        self._removeLogicalVolume(self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX),
                                  perform_on_nodes=True)

    @Pyro4.expose()
    @lockingMethod()
    def initialiseMetaData(self, *args, **kwargs):
        """Provides an exposed method for _initialiseMetaData
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._initialiseMetaData(*args, **kwargs)

    def _initialiseMetaData(self):
        """Performs an initialisation of the meta data, using drbdadm"""
        System.runCommand([NodeDRBD.DRBDADM, 'create-md', self.resource_name])

    @Pyro4.expose()
    @lockingMethod()
    def drbdUp(self, *args, **kwargs):
        """Provides an exposed method for _drbdUp
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdUp(*args, **kwargs)

    def _drbdUp(self):
        """Performs a DRBD 'up' on the hard drive DRBD resource"""
        System.runCommand([NodeDRBD.DRBDADM, 'up', self.resource_name])

    @Pyro4.expose()
    @lockingMethod()
    def drbdDown(self, *args, **kwargs):
        """Provides an exposed method for _drbdDown
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdDown(*args, **kwargs)

    def _drbdDown(self):
        """Performs a DRBD 'down' on the hard drive DRBD resource"""
        try:
            System.runCommand([NodeDRBD.DRBDADM, 'down', self.resource_name])
        except MCVirtCommandException:
            import time
            # If the DRBD down fails, attempt to wait 5 seconds and try again
            time.sleep(5)
            System.runCommand([NodeDRBD.DRBDADM, 'down', self.resource_name])

    @Pyro4.expose()
    @lockingMethod()
    def drbdConnect(self, *args, **kwargs):
        """Provides an exposed method for _drbdConnect
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdConnect(*args, **kwargs)

    def _drbdConnect(self):
        """Performs a DRBD 'connect' on the hard drive DRBD resource"""
        if self._drbdGetConnectionState() not in DRBD.DRBD_STATES['CONNECTION']['CONNECTED']:
            print self._drbdGetConnectionState()
            System.runCommand([NodeDRBD.DRBDADM, 'connect', self.resource_name])

    @Pyro4.expose()
    @lockingMethod()
    def drbdDisconnect(self, *args, **kwargs):
        """Provides an exposed method for _drbdDisconnect
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdDisconnect(*args, **kwargs)

    def _drbdDisconnect(self):
        """Performs a DRBD 'disconnect' on the hard drive DRBD resource"""
        System.runCommand([NodeDRBD.DRBDADM, 'disconnect', self.resource_name])

    def _setTwoPrimariesConfig(self, allow=False):
        """Configures DRBD to temporarily allow or re-disable whether
           two allow two primaries"""
        if allow:
            # Configure DRBD on both nodes to allow DRBD volume to be set to primary
            self._checkDrbdStatus()

            System.runCommand([NodeDRBD.DRBDADM, 'net-options',
                               self.resource_name,
                               '--allow-two-primaries'])

        else:
            # Get disk role state
            local_role, remote_role = self._drbdGetRole()

            # Ensure neither states are unknown
            if (local_role is DrbdRoleState.UNKNOWN or
                    remote_role is DrbdRoleState.UNKNOWN):
                raise DrbdStateException('Cannot disable two-primaries configuration as'
                                         ' local or remote role is currently unknown')

            # Ensure that only one node has been set to primary
            if (local_role is DrbdRoleState.PRIMARY and
                    remote_role is DrbdRoleState.PRIMARY):
                raise DrbdStateException('Both nodes are set to primary whilst attempting'
                                         ' to disable dual-primary mode')

            System.runCommand([NodeDRBD.DRBDADM, 'net-options',
                               self.resource_name,
                               '--allow-two-primaries=no'])

        # Config remote node(s)
        if self._is_cluster_master:
            cluster_instance = self._get_registered_object('cluster')
            cluster_instance.runRemoteCommand(
                'virtual_machine-hard_drive-drbd-setTwoPrimariesConfig',
                {'vm_name': self.vm_object.getName(),
                 'disk_id': self.disk_id,
                 'allow': allow},
                nodes=self.vm_object._getRemoteNodes()
            )

    @Pyro4.expose()
    @lockingMethod()
    def drbdSetPrimary(self, *args, **kwargs):
        """Provides an exposed method for _drbdSetPrimary
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdSetPrimary(*args, **kwargs)

    def _drbdSetPrimary(self, allow_two_primaries=False):
        """Performs a DRBD 'primary' on the hard drive DRBD resource"""
        local_role_state, remote_role_state = self._drbdGetRole()

        # Check DRBD status
        self._checkDrbdStatus()

        # Ensure that role states are not unknown
        node_drbd = self._get_registered_object('node_drbd')
        if (local_role_state is DrbdRoleState.UNKNOWN or
            (remote_role_state is DrbdRoleState.UNKNOWN and
             not self._ignore_drbd)):
            raise DrbdStateException('DRBD role is unknown for resource %s' %
                                     self.resource_name)

        # Ensure remote role is secondary
        if (not allow_two_primaries and
            remote_role_state is not DrbdRoleState.SECONDARY and
            not (DrbdRoleState.UNKNOWN and
                 self._ignore_drbd)):
            raise DrbdStateException(
                'Cannot make local DRBD primary if remote DRBD is not secondary: %s' %
                self.resource_name)

        # Set DRBD resource to primary
        System.runCommand([NodeDRBD.DRBDADM, 'primary', self.resource_name])

    @Pyro4.expose()
    @lockingMethod()
    def drbdSetSecondary(self, *args, **kwargs):
        """Provides an exposed method for _drbdSetSecondary
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdSetSecondary(*args, **kwargs)

    def _drbdSetSecondary(self):
        """Performs a DRBD 'secondary' on the hard drive DRBD resource"""
        # Attempt to set the disk as secondary
        set_secondary_command = [NodeDRBD.DRBDADM, 'secondary',
                                 self.resource_name]
        try:
            System.runCommand(set_secondary_command)
        except MCVirtCommandException:
            # If this fails, wait for 5 seconds, and attempt once more
            from time import sleep
            sleep(5)
            System.runCommand(set_secondary_command)

    def _drbdOverwritePeer(self):
        """Force DRBD to overwrite the data on the peer"""
        System.runCommand([NodeDRBD.DRBDADM,
                           '--',
                           '--overwrite-data-of-peer',
                           'primary',
                           self.resource_name])

    def _checkDrbdStatus(self):
        """Checks the status of the DRBD volume and returns the states"""
        # Check the disk state
        local_disk_state, remote_disk_state = self._drbdGetDiskState()
        self._checkStateType('DISK', local_disk_state)

        # Check connection state
        connection_state = self._drbdGetConnectionState()
        self._checkStateType('CONNECTION', connection_state)

        # Check DRBD role
        local_role_state, remote_role_state = self._drbdGetRole()

        # Ensure the disk is in-sync
        self._ensureInSync()

        return ((local_disk_state, remote_disk_state),
                connection_state, (local_role_state, remote_role_state))

    def _checkStateType(self, state_name, state):
        """Determines if the given type of state is OK or not. An exception
           is thrown in the event of a bad state"""
        # Determine if connection state is not OK
        if state not in DRBD.DRBD_STATES[state_name]['OK']:
            # Ignore the state if it is in warning and the user has specified to ignore
            # the DRBD state
            if state in DRBD.DRBD_STATES[state_name]['WARNING']:
                if not self._ignore_drbd:
                    raise DrbdStateException(
                        ('DRBD connection state for the DRBD resource '
                         '%s is %s so cannot continue. Run MCVirt as a '
                         'superuser with --ignore-drbd to ignore this issue') %
                        (self.resource_name, state.value)
                    )
            else:
                raise DrbdStateException(
                    'DRBD connection state for the DRBD resource %s is %s so cannot continue. ' %
                    (self.resource_name, state.value)
                )

    def _drbdGetConnectionState(self):
        """Returns the connection state of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'cstate',
                                          self.resource_name])
        state = stdout.strip()
        return DrbdConnectionState(state)

    def _drbdGetDiskState(self):
        """Returns the disk state of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'dstate',
                                          self.resource_name])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdDiskState(local_state), DrbdDiskState(remote_state))

    def _drbdGetRole(self):
        """Returns the role of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'role',
                                          self.resource_name])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdRoleState(local_state), DrbdRoleState(remote_state))

    def preMigrationChecks(self):
        """Ensures that the DRBD state of the disk is in a state suitable for migration"""
        # Ensure disk state is up-to-date on both local and remote nodes
        local_disk_state, remote_disk_state = self._drbdGetDiskState()
        local_role, remote_role = self._drbdGetRole()
        connection_state = self._drbdGetConnectionState()
        if ((local_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (remote_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (connection_state is not DrbdConnectionState.CONNECTED) or
                (local_role is not DrbdRoleState.PRIMARY) or
                (remote_role is not DrbdRoleState.SECONDARY)):
            raise DrbdStateException('DRBD resource %s is not in a suitable state to be migrated. '
                                     % self.resource_name +
                                     'Both nodes must be up-to-date and connected')

    def preOnlineMigration(self, destination_node):
        """Performs required tasks in order
           for the underlying VM to perform an
           online migration"""
        # Temporarily allow the DRBD volume to be in a dual-primary mode
        self._setTwoPrimariesConfig(allow=True)

        # Set remote node as primary
        remote_disk = self.getRemoteObject(remote_node=destination_node)
        remote_disk.drbdSetPrimary(allow_two_primaries=True)

    def postOnlineMigration(self):
        """Performs post tasks after a VM
           has performed an online migration"""
        import time
        # Set DRBD on local node as secondary
        self._drbdSetSecondary()

        # Attempt to wait for DRBD to update status to secondary
        # If, after 15 seconds, the local volume is still not
        # primary, let the setTwiPrimariesConfig function raise
        # an appropriate exception
        for i in range(1, 3):
            local_role, _ = self._drbdGetRole()
            if local_role is DrbdRoleState.SECONDARY:
                break
            else:
                time.sleep(5)

        # Disable the DRBD volume from being a dual-primary mode
        self._setTwoPrimariesConfig(allow=False)

    def _ensureBlockDeviceExists(self):
        """Ensures that the DRBD block device exists"""
        drbd_block_device = self._getDrbdDevice()
        if not os.path.exists(drbd_block_device):
            raise DrbdBlockDeviceDoesNotExistException(
                'DRBD block device %s for resource %s does not exist' %
                (drbd_block_device, self.resource_name))

    def _ensureInSync(self):
        """Ensures that the DRBD volume was marked as in sync during the last verification"""
        if not self._isInSync() and not self._ignore_drbd:
            raise DrbdVolumeNotInSyncException(
                'The last DRBD verification of the DRBD volume failed: %s. ' %
                self.resource_name +
                'Run MCVirt as a superuser with --ignore-drbd to ignore this issue'
            )

    def _isInSync(self):
        """Returns whether the last DRBD verification reported the
           DRBD volume as in-sync"""
        vm_config = self.vm_object.getConfigObject().getConfig()

        # If the hard drive configuration exists, read the current state of the disk
        if self.disk_id in vm_config['hard_disks']:
            return vm_config['hard_disks'][self.disk_id]['sync_state']
        else:
            # Otherwise, if the hard drive configuration does not exist in the VM configuration,
            # assume the disk is being created and is in-sync
            return True

    @Pyro4.expose()
    @lockingMethod()
    def setSyncState(self, sync_state, update_remote=True):
        """Updates the hard drive config, marking the disk as out of sync"""
        obtained_lock = False
        def updateConfig(config):
            config['hard_disks'][self.disk_id]['sync_state'] = sync_state
        self.vm_object.getConfigObject().updateConfig(
            updateConfig,
            'Updated sync state of disk \'%s\' of \'%s\' to \'%s\'' %
            (self.disk_id,
             self.vm_object.getName(),
             sync_state))

        # Update remote nodes
        if self._is_cluster_master and update_remote:
            cluster = self._get_registered_object('cluster')
            def remoteCommand(node):
                remote_disk = self.getRemoteObject(remote_node=node)
                remote_disk.setSyncState(sync_state=sync_state)
            cluster.runRemoteCommand(callback_method=remoteCommand,
                                     nodes=self.vm_object._getRemoteNodes())

    @Pyro4.expose()
    def verify(self):
        """Performs a verification of a DRBD hard drive"""
        import time

        # Check DRBD state of disk
        if (self._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
            raise DrbdStateException(
                'DRBD resource must be connected before performing a verification: %s' %
                self.resource_name)

        # Reset the disk to be marked in a consistent state
        self.setSyncState(True)

        try:
            # Perform a drbdadm verification
            System.runCommand([NodeDRBD.DRBDADM, 'verify',
                               self.resource_name])

            # Monitor the DRBD status, until the VM has started syncing
            while True:
                if self._drbdGetConnectionState() == DrbdConnectionState.VERIFY_S:
                    break
                time.sleep(5)

            # Monitor the DRBD status, until the VM has finished syncing
            while True:
                if self._drbdGetConnectionState() != DrbdConnectionState.VERIFY_S:
                    break
                time.sleep(5)

        except Exception:
            # If an exception is thrown during the verify, mark the VM as
            # not in-sync
            self.setSyncState(False)

        if self._isInSync():
            return True
        else:
            raise DrbdVolumeNotInSyncException('The DRBD verification for \'%s\' failed' %
                                               self.resource_name)

    def move(self, destination_node, source_node):
        """Replaces a remote node for the DRBD volume with a new node
           and syncs the data"""
        cluster_instance = Cluster(self.vm_object.mcvirt_object)

        # Remove DRBD configuration from source node
        dest_node_object = cluster_instance.getRemoteNode(destination_node)

        if source_node not in cluster_instance.getFailedNodes():
            src_node_object = cluster_instance.getRemoteNode(source_node)
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDisconnect',
                                             {'vm_name': self.vm_object.getName(),
                                              'disk_id': self.disk_id})
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                             {'config': self._dumpConfig()})

            # Remove the DRBD configuration from source node
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
                                             {'config': self._dumpConfig()})

            # Remove the meta logical volume from remote node
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-removeLogicalVolume',
                                             {'config': self._dumpConfig(),
                                              'name': self._getLogicalVolumeName(
                                                  self.DRBD_META_SUFFIX),
                                              'ignore_non_existent': False})

        # Disconnect the local DRBD volume
        self._drbdDisconnect()

        # Obtain the size of the disk to be created
        disk_size = self.getSize()

        # Create the storage on the destination node
        raw_logical_volume_name = self._getLogicalVolumeName(
            self.DRBD_RAW_SUFFIX)
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': raw_logical_volume_name,
                                           'size': disk_size})

        # Activate and zero raw volume
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': raw_logical_volume_name})
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': raw_logical_volume_name,
                                           'size': disk_size})

        meta_logical_volume_name = self._getLogicalVolumeName(
            self.DRBD_META_SUFFIX)
        meta_volume_size = self._calculateMetaDataSize()
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': meta_logical_volume_name,
                                           'size': meta_volume_size})

        # Activate and zero meta volume
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': meta_logical_volume_name})
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                          {'config': self._dumpConfig(),
                                           'name': meta_logical_volume_name,
                                           'size': meta_volume_size})

        # Generate DRBD configuration on local and remote node
        self._generateDrbdConfig()
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-generateDrbdConfig',
                                          {'config': self._dumpConfig()})
        NodeDRBD(self.vm_object.mcvirt_object).adjustDRBDConfig(
            self.resource_name
        )

        # Initialise meta-data on destination node
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-initialiseMetaData',
                                          {'config': self._dumpConfig()})

        # Bring up DRBD volume on destination node
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdUp',
                                          {'config': self._dumpConfig()})

        # Set destination node to secondary
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdSetSecondary',
                                          {'vm_name': self.vm_object.getName(),
                                           'disk_id': self.disk_id})

        # Overwrite peer with data from local node
        self._drbdOverwritePeer()

        # Remove the raw logic volume from the source node
        if (source_node not in cluster_instance.getFailedNodes()):
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-removeLogicalVolume',
                                             {'config': self._dumpConfig(),
                                              'name': self._getLogicalVolumeName(
                                                  self.DRBD_RAW_SUFFIX),
                                              'ignore_non_existent': False})

    def _getAvailableDrbdPort(self):
        """Obtains the next available DRBD port"""
        # Obtain list of currently used DRBD ports
        node_drbd = self._get_registered_object('node_drbd')
        used_ports = node_drbd.getUsedDrbdPorts()
        available_port = None

        # Determine a free port
        test_port = self.INITIAL_PORT

        while (available_port is None):
            if test_port in used_ports:
                test_port += 1
            else:
                available_port = test_port

        return available_port

    def _getAvailableDrbdMinor(self):
        """Obtains the next available DRBD minor"""
        # Obtain list of currently used DRBD minors
        node_drbd = self._get_registered_object('node_drbd')
        used_minor_ids = node_drbd.getUsedDrbdMinors()
        available_minor_id = None

        # Determine a free minor
        test_minor_id = DRBD.INITIAL_MINOR

        while (available_minor_id is None):
            if test_minor_id in used_minor_ids:
                test_minor_id += 1
            else:
                available_minor_id = test_minor_id

        return available_minor_id

    def _getLogicalVolumeName(self, lv_type):
        """Returns the logical volume name for a given logical volume type"""
        return 'mcvirt_vm-%s-disk-%s-drbd-%s' % (self.vm_object.getName(), self.disk_id, lv_type)

    @property
    def resource_name(self):
        """Returns the DRBD resource name for the hard drive object"""
        return 'mcvirt_vm-%s-disk-%s' % (self.vm_object.getName(), self.disk_id)

    @property
    def drbd_minor(self):
        """Returns the DRBD port assigned to the hard drive"""
        if self._drbd_minor is None:
            self._drbd_minor = self._getAvailableDrbdMinor()

        return self._drbd_minor

    @property
    def drbd_port(self):
        """Returns the DRBD port assigned to the hard drive"""
        if self._drbd_port is None:
            self._drbd_port = self._getAvailableDrbdPort()

        return self._drbd_port

    def _getDrbdDevice(self):
        """Returns the block object path for the DRBD volume"""
        return '/dev/drbd%s' % self.drbd_minor

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        return self._getDrbdDevice()

    @Pyro4.expose()
    @lockingMethod()
    def generateDrbdConfig(self, *args, **kwargs):
        """Provides an exposed method for _generateDrbdConfig
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._generateDrbdConfig(*args, **kwargs)

    def _generateDrbdConfig(self):
        """Generates the DRBD resource configuration"""
        from Cheetah.Template import Template

        # Create configuration for use with the template
        raw_lv_path = self._getLogicalVolumePath(self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX))
        meta_lv_path = self._getLogicalVolumePath(
            self._getLogicalVolumeName(
                self.DRBD_META_SUFFIX))
        drbd_config = \
            {
                'resource_name': self.resource_name,
                'block_device_path': self._getDrbdDevice(),
                'raw_lv_path': raw_lv_path,
                'meta_lv_path': meta_lv_path,
                'drbd_port': self.drbd_port,
                'nodes': []
            }

        # Add local node to the DRBD config
        cluster_object = self._get_registered_object('cluster')
        node_template_conf = \
            {
                'name': Cluster.getHostname(),
                'ip_address': cluster_object.getClusterIpAddress()
            }
        drbd_config['nodes'].append(node_template_conf)

        # Add remote nodes to DRBD config
        for node in self.vm_object._getRemoteNodes():
            node_config = cluster_object.getNodeConfig(node)
            node_template_conf = \
                {
                    'name': node,
                    'ip_address': node_config['ip_address']
                }
            drbd_config['nodes'].append(node_template_conf)

        # Replace the variables in the template with the local DRBD configuration
        config_content = Template(file=self.DRBD_CONFIG_TEMPLATE, searchList=[drbd_config])

        # Write the DRBD configuration
        fh = open(self._getDrbdConfigFile(), 'w')
        fh.write(config_content.respond())
        fh.close()

    @Pyro4.expose()
    @lockingMethod()
    def removeDrbdConfig(self, *args, **kwargs):
        """Provides an exposed method for _removeDrbdConfig
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._removeDrbdConfig(*args, **kwargs)

    def _removeDrbdConfig(self):
        """Remove the DRBD resource configuration from the node"""
        os.remove(self._getDrbdConfigFile())

    def _getDrbdConfigFile(self):
        """Returns the path of the DRBD resource configuration file"""
        return NodeDRBD.CONFIG_DIRECTORY + '/' + self.resource_name + '.res'

    def _calculateMetaDataSize(self):
        """Determines the size of the DRBD meta volume"""
        import math

        raw_logical_volume_name = self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)
        logical_volume_path = self._getLogicalVolumePath(raw_logical_volume_name)

        # Obtain size of raw volume
        _, raw_size_sectors, _ = System.runCommand(['blockdev', '--getsz', logical_volume_path])
        raw_size_sectors = int(raw_size_sectors.strip())

        # Obtain size of sectors
        _, sector_size, _ = System.runCommand(['blockdev', '--getss', logical_volume_path])
        sector_size = int(sector_size.strip())

        # Follow the DRBD meta data calculation formula, see
        # https://drbd.linbit.com/users-guide/ch-internals.html#s-external-meta-data
        meta_size_formula_step_1 = int(math.ceil(raw_size_sectors / 262144))
        meta_size_formula_step_2 = meta_size_formula_step_1 * 8
        meta_size_sectors = meta_size_formula_step_2 + 72

        # Convert meta size in sectors to Mebibytes
        meta_size_mebibytes = math.ceil((meta_size_sectors * sector_size) / (1024 ^ 2))

        # Convert from float to int and return
        return int(meta_size_mebibytes)

    def _getMCVirtConfig(self):
        """Returns the MCVirt hard drive configuration for the DRBD hard drive"""
        config = super(DRBD, self)._getMCVirtConfig()
        config['drbd_port'] = self.drbd_port
        config['drbd_minor'] = self.drbd_minor
        config['sync_state'] = self._sync_state
        return config

    def _getBackupLogicalVolume(self):
        """Returns the storage device for the backup"""
        return self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX)

    def _getBackupSnapshotLogicalVolume(self):
        """Returns the logical volume name for the backup snapshot"""
        return self._getLogicalVolumeName(self.DRBD_RAW_SUFFIX) + self.SNAPSHOT_SUFFIX

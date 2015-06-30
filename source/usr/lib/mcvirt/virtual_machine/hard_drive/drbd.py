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

from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.drbd import DRBD as ConfigDRBD
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode, DRBDSocket
from mcvirt.auth import Auth
from mcvirt.system import System, MCVirtCommandException
from mcvirt.cluster.cluster import Cluster
from mcvirt.mcvirt import MCVirtException


class DrbdStateException(MCVirtException):
    """The DRBD state is not OK"""
    pass


class DrbdBlockDeviceDoesNotExistException(MCVirtException):
    """DRBD block device does not exist"""
    pass


class DrbdVolumeNotInSyncException(MCVirtException):
    """The last DRBD verification of the volume failed"""
    pass


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
            'OK': [DrbdConnectionState.CONNECTED,
                   DrbdConnectionState.VERIFY_S,
                   DrbdConnectionState.VERIFY_T,
                   DrbdConnectionState.PAUSED_SYNC_S,
                   DrbdConnectionState.STARTING_SYNC_S,
                   DrbdConnectionState.SYNC_SOURCE,
                   DrbdConnectionState.WF_BIT_MAP_S],
            'WARNING': [DrbdConnectionState.STAND_ALONE,
                        DrbdConnectionState.DISCONNECTING,
                        DrbdConnectionState.UNCONNECTED,
                        DrbdConnectionState.BROKEN_PIPE,
                        DrbdConnectionState.NETWORK_FAILURE,
                        DrbdConnectionState.WF_CONNECTION,
                        DrbdConnectionState.WF_REPORT_PARAMS]
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

    def __init__(self, vm_object, disk_id):
        """Sets member variables"""
        # Get DRBD configuration from disk configuration
        self.config = ConfigDRBD(vm_object=vm_object, disk_id=disk_id, registered=True)
        super(DRBD, self).__init__(disk_id=disk_id)

    def _checkExists(self):
        """Ensures the required storage elements exist on the system"""
        raw_lv = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_RAW_SUFFIX
        )
        meta_lv = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_META_SUFFIX
        )
        DRBD._ensureLogicalVolumeExists(self.getConfigObject(), raw_lv)
        DRBD._ensureLogicalVolumeExists(self.getConfigObject(), meta_lv)
        return True

    def activateDisk(self):
        """Ensures that the disk is ready to be used by a VM on the local node"""
        self._ensureExists()
        raw_lv = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_RAW_SUFFIX)
        meta_lv = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_META_SUFFIX)
        DRBD._ensureLogicalVolumeActive(self.getConfigObject(), raw_lv)
        DRBD._ensureLogicalVolumeActive(self.getConfigObject(), meta_lv)
        self._checkDrbdStatus()

        # If the disk is not already set to primary, set it to primary
        if (self._drbdGetRole()[0] is not DrbdRoleState('Primary')):
            self._drbdSetPrimary()

        self._ensureBlockDeviceExists()

    def deactivateDisk(self):
        """Marks DRBD volume as secondary"""
        self._ensureExists()
        self._drbdSetSecondary()

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensureExists()
        return DRBD._getLogicalVolumeSize(
            self.getConfigObject(),
            self.getConfigObject()._getLogicalVolumeName(
                self.getConfigObject().DRBD_RAW_SUFFIX
            )
        )

    @staticmethod
    def create(vm_object, size, disk_id=None, drbd_minor=None, drbd_port=None):
        """Creates a new hard drive, attaches the disk to the VM and records the disk
        in the VM configuration"""
        # Ensure user has privileges to create a DRBD volume
        vm_object.mcvirt_object.getAuthObject().assertPermission(
            Auth.PERMISSIONS.MANAGE_DRBD,
            vm_object
        )

        # Ensure DRBD is enabled on the host
        if (not NodeDRBD.isEnabled()):
            raise DRBDNotEnabledOnNode('DRBD is not enabled on this node')

        # Obtain disk ID, DRBD minor and DRBD port if one has not been specified
        config_object = ConfigDRBD(
            vm_object=vm_object,
            disk_id=disk_id,
            drbd_minor=drbd_minor,
            drbd_port=drbd_port)

        # Create cluster object for running on remote nodes
        cluster_instance = Cluster(vm_object.mcvirt_object)

        remote_nodes = vm_object._getRemoteNodes()

        # Keep track of progress, so the storage stack can be torn down if something goes wrong
        progress = DRBD.CREATE_PROGRESS.START
        try:
            # Create DRBD raw logical volume
            raw_logical_volume_name = config_object._getLogicalVolumeName(
                config_object.DRBD_RAW_SUFFIX)
            DRBD._createLogicalVolume(config_object, raw_logical_volume_name,
                                      size, perform_on_nodes=True)
            progress = DRBD.CREATE_PROGRESS.CREATE_RAW_LV
            DRBD._activateLogicalVolume(config_object, raw_logical_volume_name,
                                        perform_on_nodes=True)

            # Zero raw logical volume
            DRBD._zeroLogicalVolume(config_object, raw_logical_volume_name,
                                    size, perform_on_nodes=True)

            # Create DRBD meta logical volume
            meta_logical_volume_name = config_object._getLogicalVolumeName(
                config_object.DRBD_META_SUFFIX
            )
            meta_logical_volume_size = config_object._calculateMetaDataSize()
            DRBD._createLogicalVolume(config_object, meta_logical_volume_name,
                                      meta_logical_volume_size, perform_on_nodes=True)
            progress = DRBD.CREATE_PROGRESS.CREATE_META_LV
            DRBD._activateLogicalVolume(config_object, meta_logical_volume_name,
                                        perform_on_nodes=True)

            # Zero meta logical volume
            DRBD._zeroLogicalVolume(config_object, meta_logical_volume_name,
                                    meta_logical_volume_size, perform_on_nodes=True)

            # Generate DRBD resource configuration
            config_object._generateDrbdConfig()
            progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG
            cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-generateDrbdConfig',
                                              {'config': config_object._dumpConfig()},
                                              nodes=remote_nodes)
            progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R

            # Setup meta data on DRBD volume
            DRBD._initialiseMetaData(config_object._getResourceName())
            cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-initialiseMetaData',
                                              {'config': config_object._dumpConfig()},
                                              nodes=remote_nodes)

            # Bring up DRBD resource
            DRBD._drbdUp(config_object)
            progress = DRBD.CREATE_PROGRESS.DRBD_UP
            cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdUp',
                                              {'config': config_object._dumpConfig()},
                                              nodes=remote_nodes)
            progress = DRBD.CREATE_PROGRESS.DRBD_UP_R

            # Wait for 5 seconds to let DRBD connect
            import time
            time.sleep(5)

            # Add to virtual machine
            DRBD._addToVirtualMachine(config_object)
            progress = DRBD.CREATE_PROGRESS.ADD_TO_VM

            # Create disk object
            hard_drive_object = DRBD(vm_object, config_object.getId())

            # Overwrite data on peer
            hard_drive_object._drbdOverwritePeer()

            # Ensure the DRBD resource is connected
            hard_drive_object._drbdConnect()
            progress = DRBD.CREATE_PROGRESS.DRBD_CONNECT
            cluster_instance.runRemoteCommand(
                'virtual_machine-hard_drive-drbd-drbdConnect', {
                    'vm_name': vm_object.getName(),
                    'disk_id': hard_drive_object.getConfigObject().getId()
                },
                nodes=remote_nodes

            )
            progress = DRBD.CREATE_PROGRESS.DRBD_CONNECT_R

            # Mark volume as primary on local node
            hard_drive_object._drbdSetPrimary()
            cluster_instance.runRemoteCommand(
                'virtual_machine-hard_drive-drbd-drbdSetSecondary',
                {
                    'vm_name': vm_object.getName(),
                    'disk_id': hard_drive_object.getConfigObject().getId()},
                nodes=remote_nodes)

            return hard_drive_object

        except Exception:
            # If the creation fails, tear down based on the progress of the creation
            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_CONNECT_R.value):
                cluster_instance.runRemoteCommand(
                    'virtual_machine-hard_drive-drbd-drbdDisconnect',
                    {
                        'vm_name': vm_object.getName(),
                        'disk_id': hard_drive_object.getConfigObject().getId()})

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_CONNECT.value):
                hard_drive_object._drbdDisconnect()

            if (progress.value >= DRBD.CREATE_PROGRESS.ADD_TO_VM.value):
                DRBD._removeFromVirtualMachine(config_object)

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_UP_R.value):
                cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                                  {'config': config_object._dumpConfig()},
                                                  nodes=remote_nodes)

            if (progress.value >= DRBD.CREATE_PROGRESS.DRBD_UP.value):
                DRBD._drbdDown(config_object)

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R.value):
                cluster_instance.runRemoteCommand(
                    'virtual_machine-hard_drive-drbd-removeDrbdConfig',
                    {
                        'config': config_object._dumpConfig()},
                    nodes=remote_nodes)

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG.value):
                config_object._removeDrbdConfig()

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_META_LV.value):
                DRBD._removeLogicalVolume(
                    config_object,
                    meta_logical_volume_name,
                    perform_on_nodes=True)

            if (progress.value >= DRBD.CREATE_PROGRESS.CREATE_RAW_LV.value):
                DRBD._removeLogicalVolume(
                    config_object,
                    raw_logical_volume_name,
                    perform_on_nodes=True)

            raise

    def _removeStorage(self):
        """Removes the backing storage for the DRBD hard drive"""
        self._ensureExists()
        cluster_instance = Cluster(self.getVmObject().mcvirt_object)
        remote_nodes = self.getVmObject()._getRemoteNodes()

        # Disconnect and perform a 'down' on the DRBD volume on all nodes
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDisconnect',
                                          {'vm_name': self.getVmObject().getName(),
                                           'disk_id': self.getConfigObject().getId()},
                                          nodes=remote_nodes)
        self._drbdDisconnect()
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                          {'config': self.getConfigObject()._dumpConfig()},
                                          nodes=remote_nodes)
        DRBD._drbdDown(self.getConfigObject())

        # Remove the DRBD configuration from all nodes
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
                                          {'config': self.getConfigObject()._dumpConfig()},
                                          nodes=remote_nodes)
        self.getConfigObject()._removeDrbdConfig()

        # Remove the meta and raw logical volume from all nodes
        DRBD._removeLogicalVolume(
            self.getConfigObject(),
            self.getConfigObject()._getLogicalVolumeName(
                self.getConfigObject().DRBD_META_SUFFIX),
            perform_on_nodes=True)
        DRBD._removeLogicalVolume(
            self.getConfigObject(),
            self.getConfigObject()._getLogicalVolumeName(
                self.getConfigObject().DRBD_RAW_SUFFIX),
            perform_on_nodes=True)

    @staticmethod
    def _initialiseMetaData(resource_name):
        """Performs an initialisation of the meta data, using drbdadm"""
        System.runCommand([NodeDRBD.DRBDADM, 'create-md', resource_name])

    @staticmethod
    def _drbdUp(config_object):
        """Performs a DRBD 'up' on the hard drive DRBD resource"""
        System.runCommand([NodeDRBD.DRBDADM, 'up', config_object._getResourceName()])

    @staticmethod
    def _drbdDown(config_object):
        """Performs a DRBD 'down' on the hard drive DRBD resource"""
        try:
            System.runCommand([NodeDRBD.DRBDADM, 'down', config_object._getResourceName()])
        except MCVirtCommandException:
            import time
            # If the DRBD down fails, attempt to wait 5 seconds and try again
            time.sleep(5)
            System.runCommand([NodeDRBD.DRBDADM, 'down', config_object._getResourceName()])

    def _drbdConnect(self):
        """Performs a DRBD 'connect' on the hard drive DRBD resource"""
        if (self._drbdGetConnectionState() is not DrbdConnectionState.CONNECTED):
            System.runCommand(
                [NodeDRBD.DRBDADM, 'connect', self.getConfigObject()._getResourceName()])

    def _drbdDisconnect(self):
        """Performs a DRBD 'disconnect' on the hard drive DRBD resource"""
        System.runCommand(
            [NodeDRBD.DRBDADM, 'disconnect', self.getConfigObject()._getResourceName()])

    def _drbdSetPrimary(self):
        """Performs a DRBD 'primary' on the hard drive DRBD resource"""
        local_role_state, remote_role_state = self._drbdGetRole()

        # Check DRBD status
        self._checkDrbdStatus()

        # Ensure that role states are not unknown
        if (local_role_state is DrbdRoleState.UNKNOWN or
            (remote_role_state is DrbdRoleState.UNKNOWN and
             not NodeDRBD.isIgnored(self.getVmObject().mcvirt_object))):
            raise DrbdStateException('DRBD role is unknown for resource %s' %
                                     self.getConfigObject()._getResourceName())

        # Ensure remote role is secondary
        if (remote_role_state is not DrbdRoleState.SECONDARY and
            not (DrbdRoleState.UNKNOWN and
                 NodeDRBD.isIgnored(self.getVmObject().mcvirt_object))):
            raise DrbdStateException(
                'Cannot make local DRBD primary if remote DRBD is not secondary: %s' %
                self.getConfigObject()._getResourceName())

        # Set DRBD resource to primary
        System.runCommand([NodeDRBD.DRBDADM, 'primary', self.getConfigObject()._getResourceName()])

    def _drbdSetSecondary(self):
        """Performs a DRBD 'secondary' on the hard drive DRBD resource"""
        System.runCommand(
            [NodeDRBD.DRBDADM, 'secondary', self.getConfigObject()._getResourceName()])

    def _drbdOverwritePeer(self):
        """Force DRBD to overwrite the data on the peer"""
        System.runCommand([NodeDRBD.DRBDADM,
                           '--',
                           '--overwrite-data-of-peer',
                           'primary',
                           self.getConfigObject()._getResourceName()])

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
        if (state not in DRBD.DRBD_STATES[state_name]['OK']):
            # Ignore the state if it is in warning and the user has specified to ignore
            # the DRBD state
            if (state in DRBD.DRBD_STATES[state_name]['WARNING']):
                if (not NodeDRBD.isIgnored(self.getVmObject().mcvirt_object)):
                    raise DrbdStateException(
                        ('DRBD connection state for the DRBD resource '
                         '%s is %s so cannot continue. Run MCVirt as a '
                         'superuser with --ignore-drbd to ignore this issue') %
                        (self.getConfigObject()._getResourceName(), state.value)
                    )
            else:
                raise DrbdStateException(
                    'DRBD connection state for the DRBD resource %s is %s so cannot continue. ' %
                    (self.getConfigObject()._getResourceName(), state.value))

    def _drbdGetConnectionState(self):
        """Returns the connection state of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'cstate',
                                          self.getConfigObject()._getResourceName()])
        state = stdout.strip()
        return DrbdConnectionState(state)

    def _drbdGetDiskState(self):
        """Returns the disk state of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'dstate',
                                          self.getConfigObject()._getResourceName()])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdDiskState(local_state), DrbdDiskState(remote_state))

    def _drbdGetRole(self):
        """Returns the role of the DRBD resource"""
        _, stdout, _ = System.runCommand([NodeDRBD.DRBDADM, 'role',
                                          self.getConfigObject()._getResourceName()])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdRoleState(local_state), DrbdRoleState(remote_state))

    def offlineMigrateCheckState(self):
        """Ensures that the DRBD state of the disk is in a state suitable for offline migration"""
        # Ensure disk state is up-to-date on both local and remote nodes
        local_disk_state, remote_disk_state = self._drbdGetDiskState()
        connection_state = self._drbdGetConnectionState()
        if ((local_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (remote_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (connection_state is not DrbdConnectionState.CONNECTED)):
            raise DrbdStateException('DRBD resource %s is not in a suitable state to be migrated. '
                                     % self.getConfigObject()._getResourceName() +
                                     'Both nodes must be up-to-date and connected')

    def _ensureBlockDeviceExists(self):
        """Ensures that the DRBD block device exists"""
        drbd_block_device = self.getConfigObject()._getDrbdDevice()
        if (not os.path.exists(drbd_block_device)):
            raise DrbdBlockDeviceDoesNotExistException(
                'DRBD block device %s for resource %s does not exist' %
                (drbd_block_device, self.getConfigObject()._getResourceName()))

    def _ensureInSync(self):
        """Ensures that the DRBD volume was marked as in sync during the last verification"""
        if (not self._isInSync() and not NodeDRBD.isIgnored(self.getVmObject().mcvirt_object)):
            raise DrbdVolumeNotInSyncException(
                'The last DRBD verification of the DRBD volume failed: %s. ' %
                self.getConfigObject()._getResourceName() +
                'Run MCVirt as a superuser with --ignore-drbd to ignore this issue'
            )

    def _isInSync(self):
        """Returns whether the last DRBD verification reported the
           DRBD volume as in-sync"""
        vm_config = self.getVmObject().getConfigObject().getConfig()

        # If the hard drive configuration exists, read the current state of the disk
        if (self.getConfigObject().getId() in vm_config['hard_disks']):
            return vm_config['hard_disks'][self.getConfigObject().getId()]['sync_state']
        else:
            # Otherwise, if the hard drive configuration does not exist in the VM configuration,
            # assume the disk is being created and is in-sync
            return True

    def setSyncState(self, sync_state, update_remote=True):
        """Updates the hard drive config, marking the disk as out of sync"""
        obtained_lock = False
        if (not self.getVmObject().mcvirt_object.obtained_filelock):
            obtained_lock = True
            self.getVmObject().mcvirt_object.obtainLock(timeout=10, initialise_nodes=update_remote)

        def updateConfig(config):
            config['hard_disks'][self.getConfigObject().getId()]['sync_state'] = sync_state
        self.getVmObject().getConfigObject().updateConfig(
            updateConfig,
            'Updated sync state of disk \'%s\' of \'%s\' to \'%s\'' %
            (self.getConfigObject().getId(),
             self.getConfigObject().vm_object.getName(),
             sync_state))

        # Update remote nodes
        if (self.getConfigObject().vm_object.mcvirt_object.initialiseNodes() and update_remote):
            cluster_instance = Cluster(self.getConfigObject().vm_object.mcvirt_object)
            for node in self.getConfigObject().vm_object._getRemoteNodes():
                remote_object = cluster_instance.getRemoteNode(node)
                remote_object.runRemoteCommand('virtual_machine-hard_drive-drbd-setSyncState',
                                               {'vm_name': self.getVmObject().getName(),
                                                'disk_id': self.getConfigObject().getId(),
                                                'sync_state': sync_state})

        if (obtained_lock):
            self.getVmObject().mcvirt_object.releaseLock(initialise_nodes=update_remote)

    def verify(self):
        """Performs a verification of a DRBD hard drive"""
        import time

        # Check DRBD state of disk
        if (self._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
            raise DrbdStateException(
                'DRBD resource must be connected before performing a verification: %s' %
                self.getConfigObject()._getResourceName())

        self.getVmObject().mcvirt_object.releaseLock()

        # Reset the disk to be marked in a consistent state
        self.setSyncState(True)

        try:
            # Create a socket, to receive errors from DRBD about out-of-sync blocks
            drbd_socket = DRBDSocket(self.getVmObject().mcvirt_object)

            # Perform a drbdadm verification
            System.runCommand([NodeDRBD.DRBDADM, 'verify',
                               self.getConfigObject()._getResourceName()])

            # Monitor the DRBD status, until the VM has started syncing
            while True:
                if (self._drbdGetConnectionState() == DrbdConnectionState.VERIFY_S):
                    break
                time.sleep(5)

            # Monitor the DRBD status, until the VM has finished syncing
            while True:
                if (self._drbdGetConnectionState() != DrbdConnectionState.VERIFY_S):
                    break
                time.sleep(5)

            # Provide DRBD 10 seconds to run the mcvirt_drbd command, if necessary
            time.sleep(10)

            # Stop the DRBD connection socket
            drbd_socket.stop()
            time.sleep(10)
            drbd_socket.mcvirt_instance = None
            drbd_socket = None

        except Exception:
            # If an exception is thrown during the verify, mark the VM as
            # not in-sync
            self.setSyncState(False)

            # Tear down the socket
            if (drbd_socket):
                drbd_socket.mcvirt_instance = None
                drbd_socket = None
            raise

        self.getVmObject().mcvirt_object.obtainLock()

        if (self._isInSync()):
            return True
        else:
            raise DrbdVolumeNotInSyncException('The DRBD verification for \'%s\' failed' %
                                               self.getConfigObject()._getResourceName())

    def move(self, destination_node, source_node):
        """Replaces a remote node for the DRBD volume with a new node
           and syncs the data"""
        cluster_instance = Cluster(self.getVmObject().mcvirt_object)

        # Remove DRBD configuration from source node
        dest_node_object = cluster_instance.getRemoteNode(destination_node)

        if (source_node not in cluster_instance.getFailedNodes()):
            src_node_object = cluster_instance.getRemoteNode(source_node)
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDisconnect',
                                             {'vm_name': self.getVmObject().getName(),
                                              'disk_id': self.getConfigObject().getId()})
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                             {'config': self.getConfigObject()._dumpConfig()})

            # Remove the DRBD configuration from source node
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
                                             {'config': self.getConfigObject()._dumpConfig()})

            # Remove the meta logical volume from remote node
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-removeLogicalVolume',
                                             {'config': self.getConfigObject()._dumpConfig(),
                                              'name': self.getConfigObject()._getLogicalVolumeName(
                                                  self.getConfigObject().DRBD_META_SUFFIX),
                                              'ignore_non_existent': False})

        # Disconnect the local DRBD volume
        self._drbdDisconnect()

        # Obtain the size of the disk to be created
        disk_size = self.getSize()

        # Create the storage on the destination node
        raw_logical_volume_name = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_RAW_SUFFIX)
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': raw_logical_volume_name,
                                           'size': disk_size})

        # Activate and zero raw volume
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': raw_logical_volume_name})
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': raw_logical_volume_name,
                                           'size': disk_size})

        meta_logical_volume_name = self.getConfigObject()._getLogicalVolumeName(
            self.getConfigObject().DRBD_META_SUFFIX)
        meta_volume_size = self.getConfigObject()._calculateMetaDataSize()
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-createLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': meta_logical_volume_name,
                                           'size': meta_volume_size})

        # Activate and zero meta volume
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-activateLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': meta_logical_volume_name})
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-zeroLogicalVolume',
                                          {'config': self.getConfigObject()._dumpConfig(),
                                           'name': meta_logical_volume_name,
                                           'size': meta_volume_size})

        # Generate DRBD configuration on local and remote node
        self.getConfigObject()._generateDrbdConfig()
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-generateDrbdConfig',
                                          {'config': self.getConfigObject()._dumpConfig()})

        NodeDRBD.adjustDRBDConfig(self.getVmObject().mcvirt_object,
                                  self.getConfigObject()._getResourceName())

        # Initialise meta-data on destination node
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-initialiseMetaData',
                                          {'config': self.getConfigObject()._dumpConfig()})

        # Bring up DRBD volume on destination node
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdUp',
                                          {'config': self.getConfigObject()._dumpConfig()})

        # Set destination node to secondary
        dest_node_object.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdSetSecondary',
                                          {'vm_name': self.getVmObject().getName(),
                                           'disk_id': self.getConfigObject().getId()})

        # Overwrite peer with data from local node
        self._drbdOverwritePeer()

        # Remove the raw logic volume from the source node
        if (source_node not in cluster_instance.getFailedNodes()):
            src_node_object.runRemoteCommand('virtual_machine-hard_drive-removeLogicalVolume',
                                             {'config': self.getConfigObject()._dumpConfig(),
                                              'name': self.getConfigObject()._getLogicalVolumeName(
                                                  self.getConfigObject().DRBD_RAW_SUFFIX),
                                              'ignore_non_existent': False})

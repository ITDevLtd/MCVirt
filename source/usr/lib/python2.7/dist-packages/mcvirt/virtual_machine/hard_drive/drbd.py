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
import math
import Pyro4

import time
from Cheetah.Template import Template

from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.node.drbd import Drbd as NodeDrbd
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.system import System
from mcvirt.rpc.expose_method import Expose, Transaction
from mcvirt.constants import DirectoryLocation
from mcvirt.utils import get_hostname
from mcvirt.syslogger import Syslogger
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.exceptions import (DrbdStateException, DrbdBlockDeviceDoesNotExistException,
                               DrbdVolumeNotInSyncException, MCVirtCommandException,
                               DrbdNotEnabledOnNode, InvalidNodesException,
                               TooManyParametersException, ArgumentParserException,
                               VmNotRegistered, InaccessibleNodeException,
                               InsufficientSpaceException,
                               InconsistentVolumeSizeError)


class DrbdConnectionState(Enum):
    """Library of Drbd connection states"""

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
    # A Drbd connection has been established, data mirroring is now active.
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
    """Library of Drbd role states"""

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
    """Library of Drbd disk states"""

    # No local block device has been assigned to the Drbd driver. This may mean that the resource
    # has never attached to its backing device, that it has been manually detached using
    # drbdadm detach, or that it automatically detached after a lower-level I/O error.
    DISKLESS = 'Diskless'
    # Transient state while reading meta data.
    ATTACHING = 'Attaching'
    # Transient state following an I/O failure report by the local block
    # device. Next state: Diskless.
    FAILED = 'Failed'
    # Transient state when an Attach is carried out on an already-Connected Drbd device.
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


class Drbd(Base):
    """Provides operations to manage Drbd-backed hard drives, used by VMs"""

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
    DRBD_CONFIG_TEMPLATE = DirectoryLocation.TEMPLATE_DIR + '/drbd_resource.conf'
    CACHE_MODE = 'none'

    # The maximum number of storage devices for the current type
    MAXIMUM_DEVICES = 4

    def __init__(self, drbd_minor=None, drbd_port=None, *args, **kwargs):
        """Set member variables"""
        # Get Drbde configuration from disk configuration
        self._sync_state = True
        self._drbd_port = drbd_port
        self._drbd_minor = drbd_minor
        super(Drbd, self).__init__(*args, **kwargs)

    @property
    def config_properties(self):
        """Return the disk object config items"""
        return super(Drbd, self).config_properties + ['drbd_port', 'drbd_minor']

    @property
    def libvirt_device_type(self):
        """Return the libvirt device type of the storage backend.
        This is overriden from the storage backend as DRBD provides
        an independent block device.
        """
        return 'block'

    @property
    def libvirt_source_parameter(self):
        """Return the libvirt source parameter fro storage backend.
        This is overriden from the storage backend as DRBD provides
        an independent block device.
        """
        return 'dev'

    @Expose()
    def get_resource_name(self):
        """Obtain the resource name"""
        return self.resource_name

    @Expose()
    def get_drbd_port(self):
        """Obtain the DRBD port"""
        return self.drbd_port

    @Expose()
    def get_drbd_minor(self):
        """Obtain the DRBD minor ID"""
        return self.drbd_minor

    @staticmethod
    def isAvailable(storage_factory, node_drdb):
        """Determine if Drbd is available on the node"""
        return (storage_factory.get_all(drbd=True,
                                        available_on_local_node=True) and
                node_drdb.is_enabled())

    @Expose()
    def get_raw_volume(self):
        """Return a volume object for the raw volume"""
        return self._get_volume(self._get_volume_name(self.DRBD_RAW_SUFFIX))

    @Expose()
    def get_meta_volume(self):
        """Return a volume object for the raw volume"""
        return self._get_volume(self._get_volume_name(self.DRBD_META_SUFFIX))

    def _check_exists(self):
        """Check the required storage elements exist on the system"""
        return bool(self.get_raw_volume().check_exists() and
                    self.get_meta_volume().check_exists())

    def is_static(self):
        """Determine if storage is static and VM cannot be
        migrated to any node in the cluster
        """
        # All DRBD storage is static, as DRBD is confined to
        # two nodes
        return True

    def activateDisk(self):
        """Ensure that the disk is ready to be used by a VM on the local node"""
        self._ensure_exists()

        # Ensure that meta and data volumes are active
        self.get_raw_volume().ensure_active()
        self.get_meta_volume().ensure_active()
        self._checkDrbdStatus()

        # If the disk is not already set to primary, set it to primary
        if self._drbdGetRole()[0] is not DrbdRoleState('Primary'):
            self._drbdSetPrimary()

        self._ensureBlockDeviceExists()

    def deactivateDisk(self):
        """Marks Drbd volume as secondary"""
        self._ensure_exists()
        self._drbdSetSecondary()

    def getSize(self):
        """Gets the size of the disk (in MB)"""
        self._ensure_exists()
        return self.get_raw_volume().get_size()

    def create(self, size):
        """Creates a new hard drive, attaches the disk to the VM and records the disk
        in the VM configuration"""
        # Ensure user has privileges to create a Drbd volume
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)

        # Ensure Drbd is enabled on the host
        if not self._get_registered_object('node_drbd').is_enabled():
            raise DrbdNotEnabledOnNode('Drbd is not enabled on this node')

        # Get remote nodes - can assume that this is just 1 since DRBD only support two nodes
        remote_nodes = self.vm_object._get_remote_nodes()
        nodes = list(remote_nodes) + [get_hostname()]
        if len(remote_nodes) != 1:
            raise InvalidNodesException('Only one remote node can be used')

        t = Transaction()

        # Ensure DRBD port is determined before obtaining a remote object
        self.drbd_port

        raw_volume = self.get_raw_volume()
        raw_volume.create(size, nodes=nodes)

        raw_volume.activate(nodes=nodes)

        # Zero raw logical volume
        raw_volume.wipe(nodes=nodes)

        # Create Drbd meta logical volume
        meta_volume_size = self._calculateMetaDataSize()
        meta_volume = self.get_meta_volume()
        meta_volume.create(meta_volume_size, nodes=nodes)

        meta_volume.activate(nodes=nodes)

        # Zero meta logical volume
        meta_volume.wipe(nodes=nodes)

        # Generate Drbd resource configuration
        self._generateDrbdConfig(
            nodes=nodes, get_remote_object_kwargs={'registered': False})

        # Setup meta data on Drbd volume
        self._initialiseMetaData(
            nodes=nodes, get_remote_object_kwargs={'registered': False})

        # Bring up Drbd resource
        self._drbdUp(
            nodes=nodes, get_remote_object_kwargs={'registered': False})

        # Wait for 5 seconds to let Drbd initialise
        # TODO: Monitor Drbd status instead.
        time.sleep(5)

        # Add to virtual machine
        self._sync_state = True
        self.addToVirtualMachine(
            nodes=nodes, get_remote_object_kwargs={'registered': False})

        # Overwrite data on peer
        self._drbdOverwritePeer()

        # Ensure the Drbd resource is connected
        self._drbdConnect(nodes=nodes)

        # Mark volume as primary on local node
        self._drbdSetPrimary()

        self.drbdSetSecondary(nodes=remote_nodes)

        t.finish()

    def removeStorage(self, *args, **kwargs):
        """Exposed method for _removeStorage"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')
        return self._removeStorage(*args, **kwargs)

    def _removeStorage(self, local_only=False, remove_raw=True):
        """Removes the backing storage for the Drbd hard drive"""
        self._ensure_exists()
        cluster = self._get_registered_object('cluster')
        remote_nodes = [] if local_only else self.vm_object._get_remote_nodes()
        all_nodes = ([get_hostname()]
                     if local_only else
                     self.vm_object.getAvailableNodes())

        # Disconnect and perform a 'down' on the Drbd volume on all nodes
        def remoteCommand(node):
            remote_disk = self.get_remote_object(node_object=node, registered=False)
            remote_disk.drbdDisconnect()
        cluster.run_remote_command(callback_method=remoteCommand,
                                   nodes=remote_nodes)
        self._drbdDisconnect()

        def remoteCommand(node):
            remote_disk = self.get_remote_object(node_object=node, registered=False)
            remote_disk.drbdDown()
        cluster.run_remote_command(callback_method=remoteCommand,
                                   nodes=remote_nodes)
        self._drbdDown()

        # Remove the Drbd configuration from all nodes
        def remoteCommand(node):
            remote_disk = self.get_remote_object(node_object=node, registered=False)
            remote_disk.removeDrbdConfig()
        cluster.run_remote_command(callback_method=remoteCommand,
                                   nodes=remote_nodes)
        self._removeDrbdConfig()

        # Remove the meta and raw logical volume from all nodes
        self.get_meta_volume().delete(nodes=all_nodes)
        if remove_raw:
            self.get_raw_volume().delete(nodes=all_nodes)

    @Expose(locking=True)
    def initialiseMetaData(self, *args, **kwargs):
        """Provides an exposed method for _initialiseMetaData
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._initialiseMetaData(*args, **kwargs)

    @Expose(expose=False, remote_method='initialiseMetaData',
            remote_nodes=True)
    def _initialiseMetaData(self):
        """Performs an initialisation of the meta data, using drbdadm"""
        System.runCommand([NodeDrbd.DrbdADM, 'create-md', self.resource_name])

    def _ensure_consistent_volumes_size(self):
        """Ensure that raw and meta volumes are a consistent size
        across the cluster
        """
        raw_sizes = self.get_raw_volume().get_size(nodes=self.vm_object.getAvailableNodes(),
                                                   return_dict=True)
        if raw_sizes.values()[0] != raw_sizes.values()[1]:
            raise InconsistentVolumeSizeError('Raw volumes for %s are not the same across nodes' %
                                              self.get_raw_volume().name)

        meta_sizes = self.get_meta_volume().get_size(nodes=self.vm_object.getAvailableNodes(),
                                                     return_dict=True)
        if meta_sizes.values()[0] != meta_sizes.values()[1]:
            raise InconsistentVolumeSizeError('Raw volumes for %s are not the same across nodes' %
                                              self.get_meta_volume().name)

    @Expose(locking=True)
    def increaseSize(self, increase_size):
        """Increases the size of a VM hard drive, given the size to increase the drive by"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_VM, self.vm_object
        )

        # Ensure disks are the same size
        self._ensure_consistent_volumes_size()

        # Ensure increase_size is a valid positive integer
        ArgumentValidator.validate_positive_integer(increase_size)

        # Ensure that there is enough free space on the storage backend
        # for the increased size (excluding meta data)
        # @TODO Also ensure there's enough free space for meta data
        free_space = self.get_storage_backend().get_free_space(
            nodes=self.vm_object.getAvailableNodes(), return_dict=True)

        for node in free_space:
            if free_space[node] < increase_size:
                raise InsufficientSpaceException('Attempted to increase disk by %iMB, '
                                                 'but there is only %i MB of free space '
                                                 'available in storage backend \'%s\' '
                                                 'on node %s.' %
                                                 (increase_size, free_space[node],
                                                  self.get_storage_backend().name,
                                                  node))

        # Ensure that the DRBD volume is in a valid, connected state.
        self._checkDrbdStatus()

        # Disconnect DRBD volume
        self._drbdDisconnect()

        # Obtain list of nodes
        nodes = self.vm_object.getAvailableNodes()

        # Increase size of RAW volume
        self.get_raw_volume().resize(increase_size,
                                     increase=True,
                                     nodes=nodes)

        # Recalculate META volume size
        meta_logical_volume_size = self._calculateMetaDataSize()

        # Resize META volume
        self.get_meta_volume().resize(meta_logical_volume_size,
                                      increase=True,
                                      nodes=nodes)

        # Resize DRBD volume
        self._drbd_resize()
        cluster = self._get_registered_object('cluster')

        def remoteCommand(node):
            remote_disk = self.get_remote_object(node_object=node)
            remote_disk.drbd_resize()
        cluster.run_remote_command(callback_method=remoteCommand,
                                   nodes=self.vm_object._get_remote_nodes())

        # Ensure taht volumes are the same size after resize
        self._ensure_consistent_volumes_size()

        # Re-Connect DRBD volume
        self._drbdConnect()

    @Expose(locking=True)
    def drbd_resize(self, *args, **kwargs):
        """Provides an exposed method for _drbd_resize
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbd_resize(*args, **kwargs)

    def _drbd_resize(self):
        """Performs a Drbd 'up' on the hard drive Drbd resource"""
        System.runCommand([NodeDrbd.DrbdADM, 'resize', self.resource_name])

    @Expose(locking=True)
    def drbdUp(self, *args, **kwargs):
        """Provides an exposed method for _drbdUp
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdUp(*args, **kwargs)

    @Expose(expose=False, remote_method='drbdUp', undo_method='_drbdDown',
            remote_undo_method='drbdDown', remote_nodes=True)
    def _drbdUp(self):
        """Performs a Drbd 'up' on the hard drive Drbd resource"""
        System.runCommand([NodeDrbd.DrbdADM, 'up', self.resource_name])

    @Expose(locking=True)
    def drbdDown(self, *args, **kwargs):
        """Provides an exposed method for _drbdDown
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdDown(*args, **kwargs)

    def _drbdDown(self):
        """Performs a Drbd 'down' on the hard drive Drbd resource"""
        try:
            System.runCommand([NodeDrbd.DrbdADM, 'down', self.resource_name])
        except MCVirtCommandException:
            # If the Drbd down fails, attempt to wait 5 seconds and try again
            time.sleep(5)
            System.runCommand([NodeDrbd.DrbdADM, 'down', self.resource_name])

    @Expose(locking=True)
    def drbdConnect(self, *args, **kwargs):
        """Provides an exposed method for _drbdConnect
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdConnect(*args, **kwargs)

    @Expose(locking=True, expose=False, remote_nodes=True,
            remote_method='drbdConnect', undo_method='_drbdDisconnect',
            remote_undo_method='drbdDisconnect')
    def _drbdConnect(self):
        """Performs a Drbd 'connect' on the hard drive Drbd resource"""
        if self._drbdGetConnectionState() not in Drbd.DRBD_STATES['CONNECTION']['CONNECTED']:
            System.runCommand([NodeDrbd.DrbdADM, 'connect', self.resource_name])

    @Expose(locking=True)
    def drbdDisconnect(self, *args, **kwargs):
        """Provides an exposed method for _drbdDisconnect
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdDisconnect(*args, **kwargs)

    def _drbdDisconnect(self):
        """Performs a Drbd 'disconnect' on the hard drive Drbd resource"""
        System.runCommand([NodeDrbd.DrbdADM, 'disconnect', self.resource_name])

    @Expose(locking=True)
    def setTwoPrimariesConfig(self, *args, **kwargs):
        """Provides an exposed method for _setTwoPrimariesConfig
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._setTwoPrimariesConfig(*args, **kwargs)

    def _setTwoPrimariesConfig(self, allow=False):
        """Configures Drbd to temporarily allow or re-disable whether
           two allow two primaries"""
        if allow:
            # Configure Drbd on both nodes to allow Drbd volume to be set to primary
            self._checkDrbdStatus()

            System.runCommand([NodeDrbd.DrbdADM, 'net-options',
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

            System.runCommand([NodeDrbd.DrbdADM, 'net-options',
                               self.resource_name,
                               '--allow-two-primaries=no'])

        # Configure remote node(s)
        if self._is_cluster_master:
            cluster_instance = self._get_registered_object('cluster')

            def remoteCommand(node):
                remote_disk = self.get_remote_object(node_object=node)
                remote_disk.setTwoPrimariesConfig(allow=allow)
            cluster_instance.run_remote_command(callback_method=remoteCommand,
                                                nodes=self.vm_object._get_remote_nodes())

    @Expose(locking=True)
    def drbdSetPrimary(self, *args, **kwargs):
        """Provides an exposed method for _drbdSetPrimary
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdSetPrimary(*args, **kwargs)

    def _drbdSetPrimary(self, allow_two_primaries=False):
        """Performs a Drbd 'primary' on the hard drive Drbd resource"""
        local_role_state, remote_role_state = self._drbdGetRole()

        # Check Drbd status
        self._checkDrbdStatus()

        # Ensure that role states are not unknown
        if (local_role_state is DrbdRoleState.UNKNOWN or
            (remote_role_state is DrbdRoleState.UNKNOWN and
             not self._ignore_drbd)):
            raise DrbdStateException('Drbd role is unknown for resource %s' %
                                     self.resource_name)

        # Ensure remote role is secondary
        if (not allow_two_primaries and
            remote_role_state is not DrbdRoleState.SECONDARY and
            not (DrbdRoleState.UNKNOWN and
                 self._ignore_drbd)):
            raise DrbdStateException(
                'Cannot make local Drbd primary if remote Drbd is not secondary: %s' %
                self.resource_name)

        # Set Drbd resource to primary
        System.runCommand([NodeDrbd.DrbdADM, 'primary', self.resource_name])

    @Expose(locking=True, remote_nodes=True)
    def drbdSetSecondary(self, *args, **kwargs):
        """Provides an exposed method for _drbdSetSecondary
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._drbdSetSecondary(*args, **kwargs)

    def _drbdSetSecondary(self):
        """Performs a Drbd 'secondary' on the hard drive Drbd resource"""
        # Attempt to set the disk as secondary
        set_secondary_command = [NodeDrbd.DrbdADM, 'secondary',
                                 self.resource_name]
        try:
            System.runCommand(set_secondary_command)
        except MCVirtCommandException:
            # If this fails, wait for 5 seconds, and attempt once more
            time.sleep(5)
            System.runCommand(set_secondary_command)

    def _drbdOverwritePeer(self):
        """Force Drbd to overwrite the data on the peer"""
        System.runCommand([NodeDrbd.DrbdADM,
                           '--',
                           '--overwrite-data-of-peer',
                           'primary',
                           self.resource_name])

    def _checkDrbdStatus(self):
        """Checks the status of the Drbd volume and returns the states"""
        # Check the disk state
        local_disk_state, remote_disk_state = self._drbdGetDiskState()
        self._checkStateType('DISK', local_disk_state)

        # Check connection state
        connection_state = self._drbdGetConnectionState()
        self._checkStateType('CONNECTION', connection_state)

        # Check Drbd role
        local_role_state, remote_role_state = self._drbdGetRole()

        # Ensure the disk is in-sync
        self._ensureInSync()

        return ((local_disk_state, remote_disk_state),
                connection_state, (local_role_state, remote_role_state))

    def _checkStateType(self, state_name, state):
        """Determines if the given type of state is OK or not. An exception
           is thrown in the event of a bad state"""
        # Determine if connection state is not OK
        if state not in Drbd.DRBD_STATES[state_name]['OK']:
            # Ignore the state if it is in warning and the user has specified to ignore
            # the Drbd state
            if state in Drbd.DRBD_STATES[state_name]['WARNING']:
                if not self._ignore_drbd:
                    raise DrbdStateException(
                        ('Drbd connection state for the Drbd resource '
                         '%s is %s so cannot continue. Run MCVirt as a '
                         'superuser with --ignore-drbd to ignore this issue') %
                        (self.resource_name, state.value)
                    )
            else:
                raise DrbdStateException(
                    'Drbd connection state for the Drbd resource %s is %s so cannot continue. ' %
                    (self.resource_name, state.value)
                )

    @Expose()
    def drbdGetConnectionState(self):
        """Provide an exposed method for _drbdGetConnectionState"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)
        connection_state = self._drbdGetConnectionState()
        return connection_state.name, connection_state.value

    def _drbdGetConnectionState(self):
        """Returns the connection state of the Drbd resource"""
        _, stdout, _ = System.runCommand([NodeDrbd.DrbdADM, 'cstate',
                                          self.resource_name])
        state = stdout.strip()
        return DrbdConnectionState(state)

    @Expose()
    def drbdGetDiskState(self):
        """Provide an exposed method for drbdGetDiskState"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)
        local_state, remote_state = self._drbdGetDiskState()
        return (local_state.name, local_state.value), (remote_state.name, remote_state.value)

    def _drbdGetDiskState(self):
        """Returns the disk state of the Drbd resource"""
        _, stdout, _ = System.runCommand([NodeDrbd.DrbdADM, 'dstate',
                                          self.resource_name])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdDiskState(local_state), DrbdDiskState(remote_state))

    @Expose()
    def drbdGetRole(self):
        """Provide an exposed method for drbdGetRole"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)
        local_state, remote_state = self._drbdGetRole()
        return (local_state.name, local_state.value), (remote_state.name, remote_state.value)

    def _drbdGetRole(self):
        """Returns the role of the Drbd(resource"""
        _, stdout, _ = System.runCommand([NodeDrbd.DrbdADM, 'role',
                                          self.resource_name])
        states = stdout.strip()
        (local_state, remote_state) = states.split('/')
        return (DrbdRoleState(local_state), DrbdRoleState(remote_state))

    def preMigrationChecks(self):
        """Ensures that the Drbd state of the disk is in a state suitable for migration"""
        # Ensure disk state is up-to-date on both local and remote nodes
        self._checkDrbdStatus()
        local_disk_state, remote_disk_state = self._drbdGetDiskState()
        local_role, remote_role = self._drbdGetRole()
        connection_state = self._drbdGetConnectionState()
        if ((local_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (remote_disk_state is not DrbdDiskState.UP_TO_DATE) or
                (connection_state is not DrbdConnectionState.CONNECTED) or
                (local_role is not DrbdRoleState.PRIMARY) or
                (remote_role is not DrbdRoleState.SECONDARY)):
            raise DrbdStateException('Drbd resource %s is not in a suitable state to be migrated. '
                                     % self.resource_name +
                                     'Both nodes must be up-to-date and connected')

    def preOnlineMigration(self, destination_node):
        """Performs required tasks in order
           for the underlying VM to perform an
           online migration"""
        # Temporarily allow the Drbd volume to be in a dual-primary mode
        self._setTwoPrimariesConfig(allow=True)

        # Set remote node as primary
        remote_disk = self.get_remote_object(node_object=destination_node)
        remote_disk.drbdSetPrimary(allow_two_primaries=True)

    def postOnlineMigration(self):
        """Performs post tasks after a VM
           has performed an online migration"""
        # Set Drbd on local node as secondary
        self._drbdSetSecondary()

        # Attempt to wait for Drbd to update status to secondary
        # If, after 15 seconds, the local volume is still not
        # primary, let the setTwiPrimariesConfig function raise
        # an appropriate exception
        for i in range(1, 3):
            local_role, _ = self._drbdGetRole()
            if local_role is DrbdRoleState.SECONDARY:
                break
            else:
                time.sleep(5)

        # Disable the Drbd volume from being a dual-primary mode
        self._setTwoPrimariesConfig(allow=False)

    def _ensureBlockDeviceExists(self):
        """Ensures that the Drbd block device exists"""
        drbd_block_device = self._getDrbdDevice()
        if not os.path.exists(drbd_block_device):
            raise DrbdBlockDeviceDoesNotExistException(
                'Drbd block device %s for resource %s does not exist' %
                (drbd_block_device, self.resource_name))

    def _ensureInSync(self):
        """Ensures that the Drbd volume was marked as in sync during the last verification"""
        if not self._isInSync() and not self._ignore_drbd:
            raise DrbdVolumeNotInSyncException(
                'The last Drbd verification of the Drbd volume failed: %s. ' %
                self.resource_name +
                'Run MCVirt as a superuser with --ignore-drbd to ignore this issue'
            )

    @Expose()
    def isInSync(self):
        """Provides an exposed method for _isInSync"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)
        return self._isInSync()

    def _isInSync(self):
        """Returns whether the last Drbd verification reported the
           Drbd volume as in-sync"""
        vm_config = self.vm_object.get_config_object().get_config()

        # If the hard drive configuration exists, read the current state of the disk
        if self.disk_id in vm_config['hard_disks']:
            return vm_config['hard_disks'][self.disk_id]['sync_state']
        else:
            # Otherwise, if the hard drive configuration does not exist in the VM configuration,
            # assume the disk is being created and is in-sync
            return True

    @Expose(locking=True)
    def setSyncState(self, sync_state, update_remote=True):
        """Updates the hard drive config, marking the disk as out of sync"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.SET_SYNC_STATE, self.vm_object
        )

        def update_config(config):
            config['hard_disks'][self.disk_id]['sync_state'] = sync_state
        self.vm_object.get_config_object().update_config(
            update_config,
            'Updated sync state of disk \'%s\' of \'%s\' to \'%s\'' %
            (self.disk_id,
             self.vm_object.get_name(),
             sync_state))

        # Update remote nodes
        if self._is_cluster_master and update_remote:
            cluster = self._get_registered_object('cluster')

            def remoteCommand(node):
                remote_disk = self.get_remote_object(node_object=node)
                remote_disk.setSyncState(sync_state=sync_state)
            cluster.run_remote_command(callback_method=remoteCommand,
                                       nodes=self.vm_object._get_remote_nodes())

    @Expose()
    def verify(self):
        """Performs a verification of a Drbd hard drive"""
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object
        )

        if get_hostname() not in self.vm_object.getAvailableNodes():
            remote_object = self.get_remote_object(
                node=(self.vm_object.getNode() or self.vm_object.getAvailableNodes()[0]))
            return remote_object.verify()

        # Check Drbd state of disk
        if self._drbdGetConnectionState() != DrbdConnectionState.CONNECTED:
            raise DrbdStateException(
                'Drbd resource must be connected before performing a verification: %s' %
                self.resource_name)

        # Reset the disk to be marked in a consistent state
        self.setSyncState(True)

        try:
            # Perform a drbdadm verification
            System.runCommand([NodeDrbd.DrbdADM, 'verify',
                               self.resource_name])

            # Monitor the Drbd status, until the VM has started syncing
            while True:
                if self._drbdGetConnectionState() == DrbdConnectionState.VERIFY_S:
                    break
                time.sleep(5)

            # Monitor the Drbd status, until the VM has finished syncing
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
            raise DrbdVolumeNotInSyncException('The Drbd verification for \'%s\' failed' %
                                               self.resource_name)

    @Expose()
    def resync(self, source_node=None, auto_determine=False):
        """Perform a resync of a Drbd hard drive"""
        # Ensure user has privileges to create a Drbd volume
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_DRBD, self.vm_object)

        # Obtain remote object is local node is not either of the
        # available nodes for the storage
        if get_hostname() not in self.vm_object.getAvailableNodes():
            remote_object = self.get_remote_object(
                node=(self.vm_object.getNode() or self.vm_object.getAvailableNodes()[0]))
            return remote_object.resync(source_node=source_node, auto_determine=auto_determine)

        # If a source node has been defined, ensure it exists and auto_determine has not also
        # been passed
        if source_node:
            if source_node not in self.vm_object.getAvailableNodes():
                raise InvalidNodesException('Invalid node name')
            if auto_determine:
                raise TooManyParametersException(
                    'Only one of source_node an auto_determine should be specified'
                )
        else:
            if not auto_determine:
                raise ArgumentParserException(
                    'Either source_node or auto_determine must be specified'
                )
            elif self.vm_object.getNode():
                source_node = self.vm_object.getNode()
            else:
                raise VmNotRegistered('Cannot auto-determine node - VM is not registered')

        # Check Drbd state of disk
        if self._drbdGetConnectionState() != DrbdConnectionState.CONNECTED:
            raise DrbdStateException(
                'Drbd resource must be connected before performing a resync: %s' %
                self.resource_name)

        if source_node == get_hostname():
            System.runCommand([NodeDrbd.DrbdADM, 'invalidate-remote',
                               self.resource_name])

            # Monitor the Drbd status, until the VM has started syncing
            while True:
                if self._drbdGetConnectionState() == DrbdConnectionState.SYNC_SOURCE:
                    break
                time.sleep(5)

            # Monitor the Drbd status, until the VM has finished syncing
            while True:
                if self._drbdGetConnectionState() != DrbdConnectionState.SYNC_SOURCE:
                    break
                time.sleep(5)
        elif not self._cluster_disable:
            remote_object = self.get_remote_object(node_object=source_node)
            remote_object.resync(source_node=source_node)

    def move(self, destination_node, source_node):
        """Replace a remote node for the Drbd volume with a new node
        and sync the data. This MUST be run on the node that will be kept
        in the cluster.
        """
        # Attempt to remove all related configuration/volume groups on source node, except
        # raw logical volume, as this would be useful in case of any failures during the rest of
        # the method.
        try:
            src_hdd_object = self.get_remote_object(node=source_node)
            src_hdd_object.removeStorage(local_only=True, remove_raw=False)

        except InaccessibleNodeException:
            Syslogger.logger().warning(('Could not connect to remote node \'%s\' - '
                                        'storage and DRBD configuration will '
                                        'still be present on node') % source_node)

        # Disconnect the local Drbd volume
        self._drbdDisconnect()

        # Obtain the size of the disk to be created
        disk_size = self.getSize()

        # Create disk object for destination node
        dest_hdd_object = self.get_remote_object(node_object=destination_node,
                                                 registered=False)

        # Create the storage on the destination node
        dest_raw_volume = dest_hdd_object.get_raw_volume()
        dest_raw_volume.create(disk_size)

        # Activate and zero raw volume
        dest_raw_volume.activate()
        dest_raw_volume.wipe()

        # Create meta volume for destination, calculate size and create
        dest_meta_volume = dest_hdd_object.get_meta_volume()
        meta_volume_size = self._calculateMetaDataSize()
        dest_meta_volume.create(meta_volume_size)

        # Activate and zero meta volume
        dest_meta_volume.activate()
        dest_meta_volume.wipe()

        # Generate Drbd configuration on local and remote node
        self._generateDrbdConfig()
        dest_hdd_object.generateDrbdConfig()
        self._get_registered_object('node_drbd').adjust_drbd_config(
            self.resource_name
        )

        # Initialise meta-data on destination node
        dest_hdd_object.initialiseMetaData()

        # Bring up Drbd volume on destination node
        dest_hdd_object.drbdUp()

        # Set destination node to secondary
        dest_hdd_object.drbdSetSecondary()

        # Overwrite peer with data from local node
        self._drbdOverwritePeer()

        # Remove the raw logic volume from the source node
        try:
            src_hdd_object = self.get_remote_object(node=source_node)
            src_hdd_object.get_raw_volume().delete()

        except:
            # Except all exceptions, as if the initial node connection at the start of the
            # method failed, this one, if the connection succeeds, will fail as the logical volume
            # will still be in use by DRBD
            Syslogger.logger().warning('Could not connect to remote node.')

    def _getAvailableDrbdPort(self):
        """Obtains the next available Drbd port"""
        # Obtain list of currently used Drbd ports
        node_drbd = self._get_registered_object('node_drbd')
        used_ports = node_drbd.get_used_drbd_ports()
        available_port = None
        node_object = self._get_registered_object('node')
        listening_ports = node_object._get_listen_ports(include_remote=True)

        # Determine a free port
        test_port = self.INITIAL_PORT

        while (available_port is None):

            if test_port in used_ports or test_port in listening_ports:
                test_port += 1
            else:
                available_port = test_port

        return available_port

    def _getAvailableDrbdMinor(self):
        """Obtains the next available Drbd minor"""
        # Obtain list of currently used Drbd minors
        node_drbd = self._get_registered_object('node_drbd')
        used_minor_ids = node_drbd.get_used_drbd_minors()
        available_minor_id = None

        # Determine a free minor
        test_minor_id = Drbd.INITIAL_MINOR

        while (available_minor_id is None):
            if test_minor_id in used_minor_ids:
                test_minor_id += 1
            else:
                available_minor_id = test_minor_id

        return available_minor_id

    def _get_volume_name(self, lv_type):
        """Returns the logical volume name for a given logical volume type"""
        return 'mcvirt_vm-%s-disk-%s-drbd-%s' % (self.vm_object.get_name(), self.disk_id, lv_type)

    @property
    def resource_name(self):
        """Returns the Drbd resource name for the hard drive object"""
        return 'mcvirt_vm-%s-disk-%s' % (self.vm_object.get_name(), self.disk_id)

    @property
    def drbd_minor(self):
        """Returns the Drbd port assigned to the hard drive"""
        if self._drbd_minor is None:
            self._drbd_minor = self._getAvailableDrbdMinor()

        return self._drbd_minor

    @property
    def drbd_port(self):
        """Returns the Drbd port assigned to the hard drive"""
        if self._drbd_port is None:
            self._drbd_port = self._getAvailableDrbdPort()

        return self._drbd_port

    def _getDrbdDevice(self):
        """Returns the block object path for the Drbd volume"""
        return '/dev/drbd%s' % self.drbd_minor

    def _getDiskPath(self):
        """Returns the path of the raw disk image"""
        return self._getDrbdDevice()

    @Expose(locking=True)
    def generateDrbdConfig(self, *args, **kwargs):
        """Provides an exposed method for _generateDrbdConfig
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._generateDrbdConfig(*args, **kwargs)

    @Expose(expose=False, remote_method='generateDrbdConfig',
            undo_method='_removeDrbdConfig',
            remote_undo_method='removeDrbdConfig',
            remote_nodes=True)
    def _generateDrbdConfig(self):
        """Generates the Drbd resource configuration"""
        # Create configuration for use with the template
        raw_lv_path = self.get_raw_volume().get_path()
        meta_lv_path = self.get_meta_volume().get_path()
        drbd_config = \
            {
                'resource_name': self.resource_name,
                'block_device_path': self._getDrbdDevice(),
                'raw_lv_path': raw_lv_path,
                'meta_lv_path': meta_lv_path,
                'drbd_port': self.drbd_port,
                'nodes': []
            }

        # Add local node to the Drbd config
        cluster_object = self._get_registered_object('cluster')
        node_template_conf = \
            {
                'name': get_hostname(),
                'ip_address': cluster_object.get_cluster_ip_address()
            }
        drbd_config['nodes'].append(node_template_conf)

        # Add remote nodes to Drbd config
        for node in self.vm_object._get_remote_nodes():
            node_config = cluster_object.get_node_config(node)
            node_template_conf = \
                {
                    'name': node,
                    'ip_address': node_config['ip_address']
                }
            drbd_config['nodes'].append(node_template_conf)

        # Replace the variables in the template with the local Drbd configuration
        config_content = Template(file=self.DRBD_CONFIG_TEMPLATE, searchList=[drbd_config])

        # Write the Drbd configuration
        fh = open(self._getDrbdConfigFile(), 'w')
        fh.write(config_content.respond())
        fh.close()

    @Expose(locking=True)
    def removeDrbdConfig(self, *args, **kwargs):
        """Provides an exposed method for _removeDrbdConfig
           with permission checking"""
        self._get_registered_object('auth').assert_user_type('ClusterUser')

        return self._removeDrbdConfig(*args, **kwargs)

    def _removeDrbdConfig(self):
        """Remove the Drbd resource configuration from the node"""
        os.remove(self._getDrbdConfigFile())

    def _getDrbdConfigFile(self):
        """Returns the path of the Drbd resource configuration file"""
        return NodeDrbd.CONFIG_DIRECTORY + '/' + self.resource_name + '.res'

    def _calculateMetaDataSize(self):
        """Determines the size of the Drbd meta volume"""
        raw_volume = self.get_raw_volume()
        raw_size_sectors = raw_volume.get_sectors()
        sector_size = raw_volume.get_sector_size()

        # Follow the Drbd meta data calculation formula, see
        # https://drbd.linbit.com/users-guide/ch-internals.html#s-external-meta-data
        meta_size_formula_step_1 = int(math.ceil(raw_size_sectors / 262144))
        meta_size_formula_step_2 = meta_size_formula_step_1 * 8
        meta_size_sectors = meta_size_formula_step_2 + 72

        # Convert meta size in sectors to Mebibytes
        meta_size_mebibytes = math.ceil((meta_size_sectors * sector_size) / (1024 ^ 2))

        # Convert from float to int and return
        return int(meta_size_mebibytes)

    def _getMCVirtConfig(self):
        """Returns the MCVirt hard drive configuration for the Drbd hard drive"""
        config = super(Drbd, self)._getMCVirtConfig()
        config['drbd_port'] = self.drbd_port
        config['drbd_minor'] = self.drbd_minor
        config['sync_state'] = self._sync_state
        return config

    def get_backup_source_volume(self):
        """Retrun the source volume for snapshotting for backeups"""
        return self.get_raw_volume()

    def get_backup_snapshot_volume(self):
        """Return a volume object for the disk object"""
        return self._get_volume(self._get_volume_name(self.DRBD_RAW_SUFFIX) + self.SNAPSHOT_SUFFIX)

#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from enum import Enum
import os

from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.drbd import DRBD as ConfigDRBD
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode
from mcvirt.auth import Auth
from mcvirt.system import System, McVirtCommandException
from mcvirt.cluster.cluster import Cluster
from mcvirt.mcvirt import McVirtException

class DrbdStateException(McVirtException):
  """The DRBD state is not OK"""
  pass


class DrbdBlockDeviceDoesNotExistException(McVirtException):
  """DRBD block device does not exist"""
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
  # TCP connection has been established, this node waits for the first network packet from the peer.
  WF_REPORT_PARAMS = 'WFReportParams'
  # A DRBD connection has been established, data mirroring is now active. This is the normal state.
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
  # Synchronization is currently running, with the local node being the source of synchronization.
  SYNC_SOURCE = 'SyncSource'
  # Synchronization is currently running, with the local node being the target of synchronization.
  SYNC_TARGET = 'SyncTarget'
  # The local node is the source of an ongoing synchronization, but synchronization is currently paused.
  # This may be due to a dependency on the completion of another synchronization process, or due to
  # synchronization having been manually interrupted by drbdadm pause-sync.
  PAUSED_SYNC_S = 'PausedSyncS'
  # The local node is the target of an ongoing synchronization, but synchronization is currently paused.
  # This may be due to a dependency on the completion of another synchronization process, or due to
  # synchronization having been manually interrupted by drbdadm pause-sync.
  PAUSED_SYNC_T = 'PausedSyncT'
  # On-line device verification is currently running, with the local node being the source of verification.
  VERIFY_S = 'VerifyS'
  # On-line device verification is currently running, with the local node being the target of verification.
  VERIFY_T = 'VerifyT'


class DrbdRoleState(Enum):
  """Library of DRBD role states"""

  # The resource is currently in the primary role, and may be read from and written to.
  # This role only occurs on one of the two nodes, unless dual-primary mode is enabled.
  PRIMARY = 'Primary'
  # The resource is currently in the secondary role. It normally receives updates from its peer
  # (unless running in disconnected mode), but may neither be read from nor written to. This role may
  # occur on one or both nodes.
  SECONDARY = 'Secondary'
  # The resource's role is currently unknown. The local resource role never has this status.
  # It is only displayed for the peer's resource role, and only in disconnected mode.
  UNKNOWN = 'Unknown'


class DrbdDiskState(Enum):
  """Library of DRBD disk states"""

  # No local block device has been assigned to the DRBD driver. This may mean that the resource has
  # never attached to its backing device, that it has been manually detached using drbdadm detach,
  # or that it automatically detached after a lower-level I/O error.
  DISKLESS = 'Diskless'
  # Transient state while reading meta data.
  ATTACHING = 'Attaching'
  # Transient state following an I/O failure report by the local block device. Next state: Diskless.
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

  CREATE_PROGRESS = Enum('CREATE_PROGRESS', ['START', 'CREATE_RAW_LV', 'CREATE_META_LV', 'CREATE_DRBD_CONFIG',
                                             'CREATE_DRBD_CONFIG_R', 'ADD_TO_VM', 'DRBD_UP', 'DRBD_UP_R'])

  DRBD_STATES = \
    {
      'CONNECTION':
      {
        'OK': [DrbdConnectionState.CONNECTED, DrbdConnectionState.VERIFY_S, DrbdConnectionState.VERIFY_T,
               DrbdConnectionState.PAUSED_SYNC_S, DrbdConnectionState.PAUSED_SYNC_T, DrbdConnectionState.STARTING_SYNC_S,
               DrbdConnectionState.SYNC_SOURCE, DrbdConnectionState.WF_BIT_MAP_S],

        'WARNING': [DrbdConnectionState.STAND_ALONE, DrbdConnectionState.DISCONNECTING, DrbdConnectionState.UNCONNECTED,
                    DrbdConnectionState.BROKEN_PIPE, DrbdConnectionState.NETWORK_FAILURE, DrbdConnectionState.WF_CONNECTION,
                    DrbdConnectionState.WF_REPORT_PARAMS]
      },
      'ROLE':
      {
        'OK': [DrbdRoleState.PRIMARY],
        'WARNING': []
      },
      'DISK':
      {
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
    raw_lv = self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_RAW_SUFFIX)
    meta_lv = self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_META_SUFFIX)
    DRBD._ensureLogicalVolumeExists(self.getConfigObject(), raw_lv)
    DRBD._ensureLogicalVolumeExists(self.getConfigObject(), meta_lv)
    return True

  def activateDisk(self):
    """Ensures that the disk is ready to be used by a VM on the local node"""
    raw_lv = self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_RAW_SUFFIX)
    meta_lv = self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_META_SUFFIX)
    DRBD._ensureLogicalVolumeActive(self.getConfigObject(), raw_lv)
    DRBD._ensureLogicalVolumeActive(self.getConfigObject(), meta_lv)
    self._checkDrbdStatus()
    self._ensureBlockDeviceExists()

  @staticmethod
  def create(vm_object, size, disk_id=None, drbd_minor=None, drbd_port=None):
    """Creates a new hard drive, attaches the disk to the VM and records the disk
    in the VM configuration"""
    # Ensure user has privileges to create a DRBD volume
    vm_object.mcvirt_object.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_DRBD)

    # Ensure DRBD is enabled on the host
    if (not NodeDRBD.isEnabled()):
      raise NodeDRBD.DRBDNotEnabledOnNode('DRBD is not enabled on this node')

    # Obtain disk ID, DRBD minor and DRBD port if one has not been specified
    config_object = ConfigDRBD(vm_object=vm_object, disk_id=disk_id, drbd_minor=drbd_minor, drbd_port=drbd_port)

    # Create cluster object for running on remote nodes
    cluster_instance = Cluster(vm_object.mcvirt_object)

    # Keep track of progress, so the storage stack can be torn down if something goes wrong
    progress = DRBD.CREATE_PROGRESS.START
    try:
      # Create DRBD raw logical volume
      raw_logical_volume_name = config_object._getLogicalVolumeName(config_object.DRBD_RAW_SUFFIX)
      DRBD._createLogicalVolume(config_object, raw_logical_volume_name, size, perform_on_nodes=True)
      progress = DRBD.CREATE_PROGRESS.CREATE_RAW_LV
      DRBD._activateLogicalVolume(config_object, raw_logical_volume_name, perform_on_nodes=True)

      # Zero raw logical volume
      DRBD._zeroLogicalVolume(config_object, raw_logical_volume_name, size, perform_on_nodes=True)

      # Create DRBD meta logical volume
      meta_logical_volume_name = config_object._getLogicalVolumeName(config_object.DRBD_META_SUFFIX)
      meta_logical_volume_size = config_object._calculateMetaDataSize()
      DRBD._createLogicalVolume(config_object, meta_logical_volume_name, meta_logical_volume_size, perform_on_nodes=True)
      progress = DRBD.CREATE_PROGRESS.CREATE_META_LV
      DRBD._activateLogicalVolume(config_object, meta_logical_volume_name, perform_on_nodes=True)

      # Zero meta logical volume
      DRBD._zeroLogicalVolume(config_object, meta_logical_volume_name, meta_logical_volume_size, perform_on_nodes=True)

      # Generate DRBD resource configuration
      config_object._generateDrbdConfig()
      progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG
      cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-generateDrbdConfig',
                                        {'config': config_object._dumpConfig()})
      progress = DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R

      # Setup meta data on DRBD volume
      DRBD._initialiseMetaData(config_object._getResourceName())
      cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-initialiseMetaData',
                                        {'config': config_object._dumpConfig()})

      # Add to virtual machine
      DRBD._addToVirtualMachine(config_object)
      progress = DRBD.CREATE_PROGRESS.ADD_TO_VM

      # Create disk object
      hard_drive_object = DRBD(vm_object, config_object.getId())

      # Bring up DRBD resource
      hard_drive_object._drbdUp()
      progress = DRBD.CREATE_PROGRESS.DRBD_UP
      cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdUp',
                                        {'vm_name': vm_object.getName(),
                                         'disk_id': hard_drive_object.getConfigObject().getId()})
      progress = DRBD.CREATE_PROGRESS.DRBD_UP_R

      # Overwrite data on peer
      hard_drive_object._drbdOverwritePeer()

      # Mark volume as primary on local node
      hard_drive_object._drbdSetPrimary()
      cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdSetSecondary',
                                        {'vm_name': vm_object.getName(),
                                         'disk_id': hard_drive_object.getConfigObject().getId()})

      return hard_drive_object

    except Exception, e:
      # If the creation fails, tear down based on the progress of the creation
      if (progress.index >= DRBD.CREATE_PROGRESS.DRBD_UP_R.index):
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDisconnect',
                                          {'vm_name': vm_object.getName(),
                                           'disk_id': hard_drive_object.getId()})
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                          {'vm_name': vm_object.getName(),
                                           'disk_id': hard_drive_object.getId()})

      if (progress.index >= DRBD.CREATE_PROGRESS.DRBD_UP.index):
        hard_drive_object._drbdDisconnect()
        hard_drive_object._drbdDown()

      if (progress.index >= DRBD.CREATE_PROGRESS.ADD_TO_VM.index):
        DRBD._removeFromVirtualMachine(config_object)

      if (progress.index >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG_R.index):
        cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
                                          {'config': config_object._dumpConfig()})

      if (progress.index >= DRBD.CREATE_PROGRESS.CREATE_DRBD_CONFIG.index):
        config_object._removeDrbdConfig()

      if (progress.index >= DRBD.CREATE_PROGRESS.CREATE_META_LV.index):
        DRBD._removeLogicalVolume(config_object, meta_logical_volume_name, perform_on_nodes=True)

      if (progress.index >= DRBD.CREATE_PROGRESS.CREATE_RAW_LV.index):
        DRBD._removeLogicalVolume(config_object, raw_logical_volume_name, perform_on_nodes=True)

      raise

  def _removeStorage(self):
    """Removes the backing storage for the DRBD hard drive"""
    cluster_instance = Cluster(self.getVmObject().mcvirt_object)

    # Disconnect and perform a 'down' on the DRBD volume on all nodes
    cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDisconnect',
                                      {'vm_name': self.getVmObject().getName(),
                                       'disk_id': self.getConfigObject().getId()})
    cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
                                      {'vm_name': self.getVmObject().getName(),
                                       'disk_id': self.getConfigObject().getId()})
    self._drbdDisconnect()
    self._drbdDown()

    # Remove the DRBD configuration from all nodes
    cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
                                      {'config': self.getConfigObject()._dumpConfig()})
    self.getConfigObject()._removeDrbdConfig()

    # Remove the meta and raw logical volume from all nodes
    DRBD._removeLogicalVolume(self.getConfigObject(),
                              self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_META_SUFFIX),
                              perform_on_nodes=True)
    DRBD._removeLogicalVolume(self.getConfigObject(),
                              self.getConfigObject()._getLogicalVolumeName(self.getConfigObject().DRBD_RAW_SUFFIX),
                              perform_on_nodes=True)

  @staticmethod
  def _addToVirtualMachine(config_object, activate=True):
    """Overrides the base function to add the hard drive to the virtual machine,
       and performs the base function on all nodes in the cluster"""
    # Create list of nodes that the hard drive was successfully added to
    successful_nodes = []
    cluster_instance = Cluster(config_object.vm_object.mcvirt_object)

    # Add to local VM
    Base._addToVirtualMachine(config_object, activate)

    # If the node cluster is initialised, update all remote node configurations
    if (config_object.vm_object.mcvirt_object.initialiseNodes()):
      try:
        for node in config_object.vm_object.getAvailableNodes():
          # Since the VM configuration contains the local node, catch it, so that there is no attempt to
          # perform a remote command to the local node
          if (node != Cluster.getHostname()):
            remote_object = cluster_instance.getRemoteNode(node)
            remote_object.runRemoteCommand('virtual_machine-hard_drive-addToVirtualMachine',
                                           {'config': config_object._dumpConfig()})
            successful_nodes.append(node)
      except Exception:
        # If the hard drive fails to be added to a node, remove it from all successful nodes
        # and remove from the local node
        for node in successful_nodes:
          remote_object = cluster_instance.getRemoteNode(node)
          remote_object.runRemoteCommand('virtual_machine-hard_drive-removeFromVirtualMachine',
                                         {'config': config_object._dumpConfig()})
        Base._removeFromVirtualMachine(config_object)
        raise

  @staticmethod
  def _removeFromVirtualMachine(config_object):
    """Overrides the base method to remove the hard drive from a VM configuration and
       performs the base function on all nodes in the cluster"""
    # Perform removal on local node
    Base._removeFromVirtualMachine(config_object)

    # If the cluster is initialised, run on all nodes that the VM is available on
    if (config_object.vm_object.mcvirt_object.initialiseNodes()):
      cluster_instance = Cluster(config_object.vm_object.mcvirt_object)
      for node in config_object.vm_object.getAvailableNodes():
          # Since the VM configuration contains the local node, catch it, so that there is no attempt to
          # perform a remote command to the local node
        if (node != Cluster.getHostname()):
          # Since the VM configuration contains the local node, catch it, so that there is no attempt to
          # perform a remote command to the local node
          remote_object = cluster_instance.getRemoteNode(node)
          remote_object.runRemoteCommand('virtual_machine-hard_drive-removeFromVirtualMachine',
                                         {'config': config_object._dumpConfig()})

  @staticmethod
  def _initialiseMetaData(resource_name):
    """Performs an initialisation of the meta data, using drbdadm"""
    System.runCommand([NodeDRBD.DRBDADM, 'create-md', resource_name])

  def _drbdUp(self):
    """Performs a DRBD 'up' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'up', self.getConfigObject()._getResourceName()])

  def _drbdDown(self):
    """Performs a DRBD 'down' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'down', self.getConfigObject()._getResourceName()])

  def _drbdConnect(self):
    """Performs a DRBD 'connect' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'connect', self.getConfigObject()._getResourceName()])

  def _drbdDisconnect(self):
    """Performs a DRBD 'disconnect' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'disconnect', self.getConfigObject()._getResourceName()])

  def _drbdSetPrimary(self):
    """Performs a DRBD 'primary' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'primary', self.getConfigObject()._getResourceName()])

  def _drbdSetSecondary(self):
    """Performs a DRBD 'secondary' on the hard drive DRBD resource"""
    System.runCommand([NodeDRBD.DRBDADM, 'secondary', self.getConfigObject()._getResourceName()])

  def _drbdOverwritePeer(self):
    """Force DRBD to overwrite the data on the peer"""
    System.runCommand([NodeDRBD.DRBDADM, '--', '--overwrite-data-of-peer', 'primary', self.getConfigObject()._getResourceName()])

  def _checkDrbdStatus(self):
    """Checks the status of the DRBD volume and returns the states"""
    # Check the disk state
    disk_state, remote_disk_state = self._drbdGetDiskState()
    self._checkStateType('DISK', disk_state)

    # Check connection state
    connection_state = self._drbdGetConnectionState()
    self._checkStateType('CONNECTION', connection_state)

    # Check DRBD role
    role_state, remote_role_state = self._drbdGetRole()
    self._checkStateType('ROLE', role_state)

    return ((disk_state, remote_disk_state), connection_state, (role_state, remote_role_statedf ))

  def _checkStateType(self, state_name, state):
    """Determines if the given type of state is OK or not. An exception
       is thrown in the event of a bad state"""
    # Determine if connection state is not OK
    if (state not in DRBD.DRBD_STATES[state_name]['OK']):
      # Ignore the state if it is in warning and the user has specified to ignore
      # the DRBD state
      if (state in DRBD.DRBD_STATES[state_name]['WARNING']):
        if (not NodeDRBD.isIgnored(self.getVmObject().mcvirt_object)):
          raise DrbdStateException('DRBD connection state for the DRBD resource %s is %s so cannot continue. ' %
                                   (self.getConfigObject()._getResourceName(), state.value) +
                                   'Run McVirt as a superuser with --ignore-drbd to ignore this issue')
      else:
        raise DrbdStateException('DRBD connection state for the DRBD resource %s is %s so cannot continue. ' %
                                 (self.getConfigObject()._getResourceName(), state.value))

  def _drbdGetConnectionState(self):
    """Returns the connection state of the DRBD resource"""
    exit_code, stdout, stderr = System.runCommand([NodeDRBD.DRBDADM, 'cstate', self.getConfigObject()._getResourceName()])
    state = stdout.strip()
    return DrbdConnectionState(state)

  def _drbdGetDiskState(self):
    """Returns the disk state of the DRBD resource"""
    exit_code, stdout, stderr = System.runCommand([NodeDRBD.DRBDADM, 'dstate', self.getConfigObject()._getResourceName()])
    states = stdout.strip()
    (local_state, remote_state) = states.split('/')
    return (DrbdDiskState(local_state), DrbdDiskState(remote_state))

  def _drbdGetRole(self):
    """Returns the role of the DRBD resource"""
    exit_code, stdout, stderr = System.runCommand([NodeDRBD.DRBDADM, 'role', self.getConfigObject()._getResourceName()])
    states = stdout.strip()
    (local_state, remote_state) = states.split('/')
    return (DrbdRoleState(local_state), DrbdRoleState(remote_state))

  def _ensureBlockDeviceExists(self):
    """Ensures that the DRBD block device exists"""
    drbd_block_device = self.getConfigObject()._getDrbdDevice()
    if (not os.path.exists(drbd_block_device)):
      raise DrbdBlockDeviceDoesNotExistException('DRBD block device %s for resource %s does not exist' %
                                                 (drbd_block_device, self.getConfigObject()._getResourceName()))

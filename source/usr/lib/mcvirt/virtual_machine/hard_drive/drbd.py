#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from enum import Enum

from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.virtual_machine.hard_drive.config.drbd import DRBD as ConfigDRBD
from mcvirt.node.drbd import DRBD as NodeDRBD, DRBDNotEnabledOnNode
from mcvirt.auth import Auth
from mcvirt.system import System, McVirtCommandException
from mcvirt.cluster.cluster import Cluster

class DRBD(Base):
  """Provides operations to manage DRBD-backed hard drives, used by VMs"""

  CREATE_PROGRESS = Enum('START', 'CREATE_RAW_LV', 'CREATE_META_LV', 'CREATE_DRBD_CONFIG', 'CREATE_DRBD_CONFIG_R',
                         'ADD_TO_VM', 'DRBD_UP', 'DRBD_UP_R', 'OVERWRITE_PEER', 'SET_ROLE')

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

    # If the cluseter is initialised, run on all nodes that the VM is available on
    if (config_object.vm_object.mcvirt_object.initialiseNodes()):
      cluster_instance = Cluster(config_object.vm_object.mcvirt_object)
      for node in config_object.vm_object.getAvailableNodes():

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
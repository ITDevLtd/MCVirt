#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from Cheetah.Template import Template
import os
import socket
import thread

from mcvirt.mcvirt import McVirt, McVirtException
from mcvirt.mcvirt_config import McVirtConfig
from mcvirt.system import System
from mcvirt.auth import Auth

class DRBDNotInstalledException(McVirtException):
  """DRBD is not installed"""
  pass


class DRBDAlreadyEnabled(McVirtException):
  """DRBD has already been enabled on this node"""
  pass


class DRBDNotEnabledOnNode(McVirtException):
  """DRBD volumes cannot be created on a node that has not been configured to use DRBD"""
  pass


class DRBD:
  """Performs configuration of DRBD on the node"""

  CONFIG_DIRECTORY = '/etc/drbd.d'
  GLOBAL_CONFIG = CONFIG_DIRECTORY + '/global_common.conf'
  GLOBAL_CONFIG_TEMPLATE = McVirt.TEMPLATE_DIR + '/drbd_global.conf'
  DRBDADM = '/sbin/drbdadm'
  INITIAL_PORT = 7789
  INITIAL_MINOR_ID = 1

  @staticmethod
  def isEnabled():
    """Determines whether DRBD is enabled on the node or not"""
    return DRBD.getConfig()['enabled']

  @staticmethod
  def isIgnored(mcvirt_instance):
    """Determines if the user has specified for DRBD state to be ignored"""
    return mcvirt_instance.ignore_drbd

  @staticmethod
  def ignoreDrbd(mcvirt_instance):
    """Sets a global parameter for ignoring DRBD state"""
    mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.CAN_IGNORE_DRBD)
    mcvirt_instance.ignore_drbd = True

  @staticmethod
  def enable(mcvirt_instance, secret=None):
    """Ensures the machine is suitable to run DRBD"""
    import os.path
    from mcvirt.auth import Auth
    from mcvirt.cluster.cluster import Cluster
    # Ensure user has the ability to manage DRBD
    mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.MANAGE_DRBD)

    # Ensure DRBD is installed
    if (not os.path.isfile(DRBD.DRBDADM)):
      raise DRBDNotInstalledException('drbdadm not found (Is the drbd8-utils package installed?)')

    if (DRBD.isEnabled() and mcvirt_instance.initialiseNodes()):
      raise DRBDAlreadyEnabled('DRBD has already been enabled on this node')

    if (secret == None):
      secret = DRBD.generateSecret()

    # Set the secret in the local configuration
    DRBD.setSecret(secret)

    if (mcvirt_instance.initialiseNodes()):
      # Enable DRBD on the remote nodes
      cluster_object = Cluster(mcvirt_instance)
      cluster_object.runRemoteCommand('node-drbd-enable', {'secret': secret})

    # Generate the global DRBD configuration
    DRBD.generateConfig(mcvirt_instance)

    # Update the local configuration
    def updateConfig(config):
      config['drbd']['enabled'] = 1
    mcvirt_config = McVirtConfig()
    mcvirt_config.updateConfig(updateConfig, 'Enabled DRBD')

  @staticmethod
  def getConfig():
    """Returns the global DRBD configuration"""
    mcvirt_config = McVirtConfig()
    if ('drbd' in mcvirt_config.getConfig().keys()):
      return mcvirt_config.getConfig()['drbd']
    else:
      return DRBD.getDefaultConfig()

  @staticmethod
  def getDefaultConfig():
    default_config = \
      {
        'enabled': 0,
        'secret': '',
        'sync_rate': '10M',
        'protocol': 'C'
      }
    return default_config

  @staticmethod
  def generateConfig(mcvirt_instance):
    """Generates the DRBD configuration"""
    # Obtain the McVirt DRBD config
    drbd_config = DRBD.getConfig()

    # Replace the variables in the template with the local DRBD configuration
    config_content = Template(file=DRBD.GLOBAL_CONFIG_TEMPLATE, searchList=[drbd_config])

    # Write the DRBD configuration
    fh = open(DRBD.GLOBAL_CONFIG, 'w')
    fh.write(config_content.respond())
    fh.close()

    # Update DRBD running configuration
    DRBD.adjustDRBDConfig(mcvirt_instance)

  @staticmethod
  def generateSecret():
    """Generates a random secret for DRBD"""
    import random
    import string

    return ''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(16)])

  @staticmethod
  def setSecret(secret):
    """Sets the DRBD configuration in the global McVirt config file"""
    def updateConfig(config):
      config['drbd']['secret'] = secret

    mcvirt_config = McVirtConfig()
    mcvirt_config.updateConfig(updateConfig, 'Set DRBD secret')

  @staticmethod
  def adjustDRBDConfig(mcvirt_instance, resource='all'):
    """Performs a DRBD adjust, which updates the DRBD running configuration"""
    if (len(DRBD.getAllDRBDHardDriveObjects(mcvirt_instance))):
      System.runCommand([DRBD.DRBDADM, 'adjust', resource])

  @staticmethod
  def getAllDrbdHardDriveObjects(mcvirt_instance):
    from mcvirt.virtual_machine.virtual_machine import VirtualMachine

    hard_drive_objects = []
    all_vms = VirtualMachine.getAllVms(mcvirt_instance)
    for vm_name in all_vms:
      vm_object = VirtualMachine(mcvirt_object=mcvirt_instance, name=vm_name)
      all_hard_drive_objects = vm_object.getDiskObjects()

      for hard_drive_object in all_hard_drive_objects:
        if (hard_drive_object.getType() is 'DRBD'):
          hard_drive_objects.append(hard_drive_object)

    return hard_drive_objects

  @staticmethod
  def getUsedDrbdPorts(mcvirt_object):
    used_ports = []

    for hard_drive_object in DRBD.getAllDrbdHardDriveObjects(mcvirt_object):
      used_ports.append(hard_drive_object.getConfigObject()._getDrbdPort())

    return used_ports

  @staticmethod
  def getUsedDrbdMinors(mcvirt_object):
    used_minors = []

    for hard_drive_object in DRBD.getAllDrbdHardDriveObjects(mcvirt_object):
      used_minors.append(hard_drive_object.getConfigObject()._getDrbdMinor())

    return used_minors

class DRBDSocket():
  """Creates a unix socket to communicate with the DRBD out-of-sync hook script"""

  SOCKET_PATH = '/var/run/lock/mcvirt/mcvirt-drbd.sock'

  def __init__(self, mcvirt_instance):
    """Stores member variables and creates thread for the socket server"""
    self.connection = None
    self.mcvirt_instance = mcvirt_instance
    self.thread = thread.start_new_thread(DRBDSocket.server, (self,))

  def __del__(self):
    """Stops the thread and tears down on object deletion"""
    self.stop()

  def stop(self):
    """Deletes the socket connection object, removes the socket file and
       the McVirt instance"""
    self.connection = None
    try:
        os.remove(self.SOCKET_PATH)
    except OSError:
        pass
    self.mcvirt_instance = None

  def server(self):
    """Listens on the socket and marks any resources as out-of-sync"""
    self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove(self.SOCKET_PATH)
    except OSError:
        pass

    self.socket.bind(self.SOCKET_PATH)
    self.socket.listen(1)
    self.connection, _ = self.socket.accept()
    drbd_resource = self.connection.recv(1024)
    if (drbd_resource):
      from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
      hard_drive_object = HardDriveFactory.getDrbdObjectByResourceName(self.mcvirt_instance, drbd_resource)
      hard_drive_object.setSyncState(False)
    self.connection.close()

    try:
        os.remove(self.SOCKET_PATH)
    except OSError:
        pass
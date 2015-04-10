#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from Cheetah.Template import Template

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
    mcvirt_config.updateConfig(updateConfig)

  @staticmethod
  def getConfig():
    """Returns the global DRBD configuration"""
    mcvirt_config = McVirtConfig()
    return mcvirt_config.getConfig()['drbd']

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
    mcvirt_config.updateConfig(updateConfig)

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
        if (hard_drive_object.getType() is DRBD.Type):
          hard_drive_objects.append(hard_drive_object)

    return hard_drive_objects

  @staticmethod
  def getUsedDrbdPorts(mcvirt_object):
    used_ports = []

    for hard_drive_object in DRBD.getAllDrbdHardDriveObjects(mcvirt_object):
      used_ports.append(hard_drive_object.getConfig()._getDrbdPort())

    return used_ports

  @staticmethod
  def getUsedDrbdMinors(mcvirt_object):
    used_minors = []

    for hard_drive_object in DRBD.getAllDrbdHardDriveObjects(mcvirt_object):
      used_minors.append(hard_drive_object.getConfig()._getMinorId())

    return used_minors
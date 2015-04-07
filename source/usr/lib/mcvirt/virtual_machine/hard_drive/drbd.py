#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
from mcvirt.virtual_machine.hard_drive.base import Base

from mcvirt.node.drbd import DRBD as DRBDNode

class DRBD(Base):

  MAXIMUM_DEVICES = 1
  TYPE = 1

  def __init__(self, vm_object, id):
    """Sets member variables"""
    super(DRBD, self).__init__(vm_object, disk_id)

  @staticmethod
  def create(vm_object, size, disk_id=None, drbd_minor=None, port=None):

    # Obtain disk ID, DRBD minor and DRBD port if one has not been specified
    if (disk_id is None):
      Base._getAvailableId(vm_object)

    if (drbd_minor is None or drbd_port is None):
      available_minor, avilable_port = _getAvailableDRBDMinorPort(vm_object.mcvirt_object)

      if (drbd_minor is None):
        drbd_minor = available_minor

      if (drbd_port is None):
        drbd_port = available_port

  @staticmethod
  def _getAvailableDRBDMinorPort(mcvirt_object):
    """Obtains the next available DRBD minor ID and port"""
    # Obtain list of currently used DRBD minors and ports
    used_ports = []
    used_minor_ids = []
    available_port = None
    available_minor_id = None

    for hard_drive_object in DRBDNode.getAllDRBDHardDiskObjects(mcvirt_object):
      used_ports.append(hard_drive_object._getPort())
      used_minor_ids.append(hard_drive_object._getMinorId())

    # Determine a free port/minor ID
    from mcvirt.node.drbd import DRBD
    test_port = DRBD.INITIAL_PORT

    while (available_port is None):
      if (test_port in used_ports):
        test_port += 1
      else:
        available_port = test_port

    test_minor_id = DRBD.INITIAL_MINOR_ID
    while (available_minor_id is None):
      if (test_minor_id in used_minor_ids):
        test_minor_id += 1
      else:
        available_minor_id = test_minor_id

    return available_minor_id, available_port

  def _getResourceName(self):
    return DRBD.getResourceName(self.vm_object, self.getId())

  @staticmethod
  def getResourceName(vm_object, disk_id):
    return 'mcvirt_vm-%s-disk-%s' % (vm_object.getName(), disk_id)

  def _getMinorId(self):
    """Returns the DRBD port assigned to the hard drive"""
    pass

  def _getPort(self):
    """Returns the DRBD port assigned to the hard drive"""
    pass
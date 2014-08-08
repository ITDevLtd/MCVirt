#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import os
from enum import Enum
from texttable import Texttable

class Auth:
  """Provides authentication and permissions for performing functions within McVirt"""

  PERMISSIONS = Enum('CHANGE_VM_POWER_STATE', 'CREATE_VM', 'MODIFY_VM', 'MANAGE_VM_USERS')

  # Set the permissions for the permissions groups
  PERMISSION_GROUPS = \
   {
     'user':
     [
       PERMISSIONS.CHANGE_VM_POWER_STATE.index
     ],
     'owner':
     [
       PERMISSIONS.CHANGE_VM_POWER_STATE.index,
       PERMISSIONS.MANAGE_VM_USERS.index
     ]
   }

  def __init__(self, mcvirt_config):
    """Sets member variables"""
    self.username = self.getUsername()
    self.checkRootPrivileges()
    self.config = mcvirt_config



  def getUsername(self):
    """Obtains the username of the current user"""
    from mcvirt import McVirtException

    # Ensure that McVirt is effectively running as root
    if (os.geteuid() == 0):

      # If SUDO_USER has been set, then it must have been run
      # as root, and this variable can be used to obtain the username
      if (os.getenv('SUDO_USER')):
        return os.getenv('SUDO_USER')

      # Else, assume that root is running the script, as this is the only
      # way to obtain an EUID of 0 without using sudo.
      else:
        return 'root'

    # If the script is not being run with root privileges, return False
    else:
      return False


  def checkRootPrivileges(self):
    """Ensures that the user is either running as root
    or using sudo"""
    from mcvirt import McVirtException
    if (not self.getUsername()):
      raise McVirtException('McVirt must be run using sudo')
    else:
      return True


  def checkPermission(self, permission_enum, vm_object = None):
    """Checks if the user has a given permission, either globally through McVirt or for a
    given VM"""
    from mcvirt import McVirtException

    # If the user is a superuser, all permissions are attached to the user
    if (self.isSuperuser()):
      return True

    # Check the global permissions configuration to determine if the user has been granted the permission
    mcvirt_permissions = self.config.getPermissionConfig()
    if (self.checkPermissionInConfig(mcvirt_permissions, self.getUsername(), permission_enum)):
      return True

    # If a vm_object has been passed, check the VM configuration file for the required permissions
    if (vm_object):
      vm_config_object = vm_object.getConfigObject()
      vm_config = vm_config_object.getPermissionConfig()

      # Determine if the user has been granted the required permissions in the VM configuration file
      if (self.checkPermissionInConfig(vm_config, self.getUsername(), permission_enum)):
        return True

    # If the permission has not been found, throw an exception explaining that
    # the user does not have permission
    raise McVirtException('User does not have the required permission: %s' % permission_enum.key)

  def checkPermissionInConfig(self, permission_config, user, permission_enum):
    """Reads a permissions config and determines if a user has a given permission"""
    # Ititerate through the permission groups on the VM
    for (permission_group, users) in permission_config.items():

      # Check that the group, defined in the VM, is defined in this class
      if (permission_group not in Auth.PERMISSION_GROUPS.keys()):
        raise McVirtException('Permissions group, defined in %s, %s, does not exist' % (vm_object.getName(), permission_group))
      else:

        # Check if user is part of the group and the group contains
        # the required permission
        if ((user in users) and \
          (permission_enum.index in Auth.PERMISSION_GROUPS[permission_group])):
            return True

    return False


  def isSuperuser(self):
    """Determines if the current user is a superuser of McVirt"""
    superusers = self.config.getConfig()['superusers']
    username = self.getUsername()
    return ((username in superusers) or (username == 'root'))


  def addUserPermissionGroup(self, vm_object, permission_group, username):
    """Adds a user to a permissions group on a VM object"""
    from mcvirt import McVirtException

    # Check if user running script is able to add users to permission group
    if (self.isSuperuser() or
      (self.checkPermission(Auth.PERMISSIONS.MANAGE_VM_USERS, vm_object) and permission_group == 'user')):

      # Check if user is already in the group
      permission_config = vm_object.config.getPermissionConfig()
      if (username not in self.getUsersInPermissionGroup(permission_group, vm_object)):

        # Add user to permission configuration for VM
        def addUserToConfig(vm_config):
          vm_config['permissions'][permission_group].append(username)

        vm_object.config.updateConfig(addUserToConfig)

        print 'Successfully added \'%s\' as \'%s\' to VM \'%s\'' % (username, permission_group, vm_object.getName())

      else:
        raise McVirtException('User \'%s\' already in group \'%s\'' % (username, permission_group))
    else:
      raise McVirtException('VM owners cannot add manager other owners')

  def deleteUserPermissionGroup(self, vm_object, permission_group, username):
    """Removes a user from a permissions group on a VM object"""
    from mcvirt import McVirtException

    # Check if user running script is able to remove users to permission group
    if (self.isSuperuser() or
      (self.checkPermission(Auth.PERMISSIONS.MANAGE_VM_USERS, vm_object) and permission_group == 'user')):

      # Check if user exists in the group
      permission_config = vm_object.config.getPermissionConfig()
      if (username in self.getUsersInPermissionGroup(permission_group, vm_object)):

        # Remove user from permission configuration for VM
        def addUserToConfig(vm_config):
          user_index = vm_config['permissions'][permission_group].index(username)
          del(vm_config['permissions'][permission_group][user_index])

        vm_object.config.updateConfig(addUserToConfig)

        print 'Successfully removed \'%s\' from \'%s\' on VM \'%s\'' % (username, permission_group, vm_object.getName())

      else:
        raise McVirtException('User \'%s\' not in group \'%s\'' % (username, permission_group))


  def getPermissionGroups(self):
    """Returns a list of user groups"""
    return Auth.PERMISSION_GROUPS.keys()


  def getUsersInPermissionGroup(self, permission_group, vm_object = None):
    from mcvirt import McVirtException
    if (vm_object):
      permission_config = vm_object.getConfigObject().getPermissionConfig()
    else:
      permission_config = self.mcvirt_config.getPermissionConfig()

    if (permission_group in permission_config.keys()):
      return permission_config[permission_group]
    else:
      raise McVirtException('Permission group \'%s\' does not exist' % permission_group)

  def getInfo(self, vm_object = None):
    """Prints permission configuration for a given user"""
    table = Texttable()
    table.header(('User Group', 'Users'))

    for permission_group in self.getPermissionGroups():

      users = self.getUsersInPermissionGroup(permission_group, vm_object)
      users_string = ','.join(users)
      table.add_row((permission_group, users_string))
    print 'Permissions:'
    print table.draw()
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

import os
from enum import Enum
from texttable import Texttable
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.mcvirt import MCVirtException


class UserNotPresentInGroup(MCVirtException):
    """User to be removed from group is not in the group"""
    pass


class InsufficientPermissionsException(MCVirtException):
    """User does not have the required permission"""
    pass


class Auth:
    """Provides authentication and permissions for performing functions within MCVirt"""

    PERMISSIONS = Enum('PERMISSIONS', ['CHANGE_VM_POWER_STATE', 'CREATE_VM', 'MODIFY_VM',
                                       'MANAGE_VM_USERS', 'VIEW_VNC_CONSOLE', 'CLONE_VM',
                                       'DELETE_CLONE', 'MANAGE_HOST_NETWORKS', 'MANAGE_CLUSTER',
                                       'MANAGE_DRBD', 'CAN_IGNORE_DRBD', 'MIGRATE_VM',
                                       'DUPLICATE_VM', 'SET_VM_LOCK', 'BACKUP_VM',
                                       'CAN_IGNORE_CLUSTER', 'MOVE_VM',
                                       'TEST_SUPERUSER_PERMISSION', 'TEST_OWNER_PERMISSION',
                                       'TEST_USER_PERMISSION'])

    # Set the permissions for the permissions groups
    PERMISSION_GROUPS = \
        {
            'user':
            [
                PERMISSIONS.CHANGE_VM_POWER_STATE,
                PERMISSIONS.VIEW_VNC_CONSOLE,
                PERMISSIONS.TEST_USER_PERMISSION
            ],
            'owner':
            [
                PERMISSIONS.CHANGE_VM_POWER_STATE,
                PERMISSIONS.MANAGE_VM_USERS,
                PERMISSIONS.VIEW_VNC_CONSOLE,
                PERMISSIONS.CLONE_VM,
                PERMISSIONS.DELETE_CLONE,
                PERMISSIONS.DUPLICATE_VM,
                PERMISSIONS.TEST_OWNER_PERMISSION
            ]
        }

    def __init__(self, username=None):
        """Sets member variables"""
        if (username):
            self.username = username
        else:
            self.username = Auth.getLogin()
        Auth.checkRootPrivileges()

    def getUsername(self):
        """Returns the username of the auth object"""
        return self.username

    @staticmethod
    def getLogin():
        """Obtains the username of the current user"""
        # Ensure that MCVirt is effectively running as root
        if (os.geteuid() == 0):

            # If SUDO_USER has been set, then it must have been run
            # using sudo, and this variable can be used to obtain the username
            if (os.getenv('SUDO_USER')):
                return os.getenv('SUDO_USER')

            # Else, assume that root is running the script, as this is the only
            # way to obtain an EUID of 0 without using sudo.
            else:
                return 'root'

        # If the script is not being run with root privileges, return False
        else:
            return False

    @staticmethod
    def checkRootPrivileges():
        """Ensures that the user is either running as root
        or using sudo"""
        if (not Auth.getLogin()):
            raise MCVirtException('MCVirt must be run using sudo')
        else:
            return True

    def assertPermission(self, permission_enum, vm_object=None):
        """Uses checkPermission function to determine if a user has a given permission
        and throws an exception if the permission is not present"""
        if (self.checkPermission(permission_enum, vm_object)):
            return True
        else:
            # If the permission has not been found, throw an exception explaining that
            # the user does not have permission
            raise InsufficientPermissionsException('User does not have the'
                                                   ' required permission: %s' %
                                                   permission_enum.name)

    def checkPermission(self, permission_enum, vm_object=None):
        """Checks if the user has a given permission, either globally through MCVirt or for a
        given VM"""
        # If the user is a superuser, all permissions are attached to the user
        if (self.isSuperuser()):
            return True

        # Check the global permissions configuration to determine
        # if the user has been granted the permission
        mcvirt_config = MCVirtConfig()
        mcvirt_permissions = mcvirt_config.getPermissionConfig()
        if (self.checkPermissionInConfig(mcvirt_permissions, self.getUsername(), permission_enum)):
            return True

        # If a vm_object has been passed, check the VM
        # configuration file for the required permissions
        if (vm_object):
            vm_config_object = vm_object.getConfigObject()
            vm_config = vm_config_object.getPermissionConfig()

            # Determine if the user has been granted the required permissions
            # in the VM configuration file
            if (self.checkPermissionInConfig(vm_config, self.getUsername(), permission_enum)):
                return True

        return False

    def checkPermissionInConfig(self, permission_config, user, permission_enum):
        """Reads a permissions config and determines if a user has a given permission"""
        # Ititerate through the permission groups on the VM
        for (permission_group, users) in permission_config.items():

            # Check that the group, defined in the VM, is defined in this class
            if (permission_group not in Auth.PERMISSION_GROUPS.keys()):
                raise MCVirtException('Permissions group, defined in %s, %s, does not exist' %
                                      (vm_object.getName(), permission_group))

            # Check if user is part of the group and the group contains
            # the required permission
            if ((user in users) and
                    (permission_enum in Auth.PERMISSION_GROUPS[permission_group])):
                return True

        return False

    def isSuperuser(self):
        """Determines if the current user is a superuser of MCVirt"""
        superusers = self.getSuperusers()
        username = self.getUsername()
        return ((username in superusers) or (username == 'root'))

    def getSuperusers(self):
        """Returns a list of superusers"""
        mcvirt_config = MCVirtConfig()
        return mcvirt_config.getConfig()['superusers']

    def addSuperuser(self, username, mcvirt_object, ignore_duplicate=None):
        """Adds a new superuser"""
        from cluster.cluster import Cluster

        # Ensure the user is a superuser
        if (not self.isSuperuser()):
            raise MCVirtException('User must be a superuser to manage superusers')

        mcvirt_config = MCVirtConfig()

        # Ensure user is not already a superuser
        if (username not in self.getSuperusers()):
            def updateConfig(config):
                config['superusers'].append(username)
            mcvirt_config.updateConfig(updateConfig, 'Added superuser \'%s\'' % username)

            if (mcvirt_object.initialiseNodes()):
                cluster_object = Cluster(mcvirt_object)
                cluster_object.runRemoteCommand('auth-addSuperuser',
                                                {'username': username})
        elif (not ignore_duplicate):
            raise MCVirtException('User \'%s\' is already a superuser' % username)

    def deleteSuperuser(self, username, mcvirt_object):
        """Removes a superuser"""
        from cluster.cluster import Cluster

        # Ensure the user is a superuser
        if (not self.isSuperuser()):
            raise MCVirtException('User must be a superuser to manage superusers')

        # Ensure user to be removed is a superuser
        if (username not in self.getSuperusers()):
            raise UserNotPresentInGroup('User \'%s\' is not a superuser' % username)

        mcvirt_config = MCVirtConfig()

        def updateConfig(config):
            config['superusers'].remove(username)
        mcvirt_config.updateConfig(updateConfig, 'Removed \'%s\' from superuser group' % username)

        if (mcvirt_object.initialiseNodes()):
            cluster_object = Cluster(mcvirt_object)
            cluster_object.runRemoteCommand('auth-deleteSuperuser',
                                            {'username': username})

    def addUserPermissionGroup(self, mcvirt_object, permission_group, username,
                               vm_object=None, ignore_duplicate=False):
        """Adds a user to a permissions group on a VM object"""
        from cluster.cluster import Cluster

        # Check if user running script is able to add users to permission group
        if not (self.isSuperuser() or
                (vm_object and self.assertPermission(Auth.PERMISSIONS.MANAGE_VM_USERS,
                                                     vm_object) and
                 permission_group == 'user')):
            raise MCVirtException('VM owners cannot add manager other owners')

        # Check if user is already in the group
        if (vm_object):
            config_object = vm_object.getConfigObject()
        else:
            config_object = MCVirtConfig()

        if (username not in self.getUsersInPermissionGroup(permission_group, vm_object)):

            # Add user to permission configuration for VM
            def addUserToConfig(config):
                config['permissions'][permission_group].append(username)

            config_object.updateConfig(addUserToConfig, 'Added user \'%s\' to group \'%s\'' %
                                                        (username, permission_group))

            if (mcvirt_object.initialiseNodes()):
                cluster_object = Cluster(mcvirt_object)
                if (vm_object):
                    vm_name = vm_object.getName()
                else:
                    vm_name = None
                cluster_object.runRemoteCommand('auth-addUserPermissionGroup',
                                                {'permission_group': permission_group,
                                                 'username': username,
                                                 'vm_name': vm_name})

        elif (not ignore_duplicate):
            raise MCVirtException('User \'%s\' already in group \'%s\'' %
                                  (username, permission_group))

    def deleteUserPermissionGroup(self, mcvirt_object, permission_group, username, vm_object=None):
        """Removes a user from a permissions group on a VM object"""
        from cluster.cluster import Cluster

        # Check if user running script is able to remove users to permission group
        if (self.isSuperuser() or
            (self.assertPermission(Auth.PERMISSIONS.MANAGE_VM_USERS, vm_object) and
             permission_group == 'user')):

            # Check if user exists in the group
            if (username in self.getUsersInPermissionGroup(permission_group, vm_object)):

                if (vm_object):
                    config_object = vm_object.getConfigObject()
                    vm_name = vm_object.getName()
                else:
                    config_object = MCVirtConfig()
                    vm_name = None

                # Remove user from permission configuration for VM
                def removeUserFromConfig(config):
                    config['permissions'][permission_group].remove(username)

                config_object.updateConfig(removeUserFromConfig,
                                           'Removed user \'%s\' from group \'%s\'' %
                                           (username, permission_group))

                if (mcvirt_object.initialiseNodes()):
                    cluster_object = Cluster(mcvirt_object)
                    cluster_object.runRemoteCommand('auth-deleteUserPermissionGroup',
                                                    {'permission_group': permission_group,
                                                     'username': username,
                                                     'vm_name': vm_name})
            else:
                raise MCVirtException('User \'%s\' not in group \'%s\'' %
                                      (username, permission_group))

    def getPermissionGroups(self):
        """Returns a list of user groups"""
        return Auth.PERMISSION_GROUPS.keys()

    def copyPermissions(self, source_vm, dest_vm):
        """Copies the permissions from a given VM to this VM.
        This functionality is used whilst cloning a VM"""
        # Obtain permission configuration for source VM
        permission_config = source_vm.getConfigObject().getPermissionConfig()

        # Add permissions configuration from source VM to destination VM
        def addUserToConfig(vm_config):
            vm_config['permissions'] = permission_config

        dest_vm.getConfigObject().updateConfig(addUserToConfig,
                                               'Copied permission from \'%s\' to \'%s\'' %
                                               (source_vm.getName(), dest_vm.getName()))

    def getUsersInPermissionGroup(self, permission_group, vm_object=None):
        """Obtains a list of users in a given group, either in the global permissions or
           for a specific VM"""
        if (vm_object):
            permission_config = vm_object.getConfigObject().getPermissionConfig()
        else:
            mcvirt_config = MCVirtConfig()
            permission_config = mcvirt_config.getPermissionConfig()

        if (permission_group in permission_config.keys()):
            return permission_config[permission_group]
        else:
            raise MCVirtException('Permission group \'%s\' does not exist' % permission_group)

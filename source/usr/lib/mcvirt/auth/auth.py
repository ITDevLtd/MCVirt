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
import Pyro4

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import (UserNotPresentInGroup, InsufficientPermissionsException,
                               UnprivilegedUserException, InvalidPermissionGroupException,
                               DuplicatePermissionException)
from mcvirt.rpc.lock import lockingMethod
from mcvirt.rpc.pyro_object import PyroObject
from permissions import PERMISSIONS, PERMISSION_GROUPS


class Auth(PyroObject):
    """Provides authentication and permissions for performing functions within MCVirt"""

    def __init__(self, mcvirt_instance):
        """Initiate object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    @staticmethod
    def checkRootPrivileges():
        """Ensures that the user is either running as root
        or using sudo"""
        if (os.geteuid() == 0):
            return True
        else:
            raise UnprivilegedUserException('MCVirt must be run using sudo')

    def check_user_type(self, *user_type_names):
        """Checks if the currently logged-in user is of a specified type"""
        user_object = self.mcvirt_instance.getSessionObject().getCurrentUserObject()
        if user_object.__class__.__name__ in user_type_names:
            return True
        else:
            return False

    def assert_user_type(self, *user_type_names):
        """Ensures that the currently logged in user is of a specified type"""
        if not self.check_user_type(*user_type_names):
            raise InsufficientPermissionsException('User must be a %s user' % user_type_name)

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

        user_object = self.mcvirt_instance.getSessionObject().getCurrentUserObject()

        # Determine if the type of user has the permissions
        if permission_enum in user_object.PERMISSIONS:
            return True

        # Check the global permissions configuration to determine
        # if the user has been granted the permission
        mcvirt_config = MCVirtConfig()
        mcvirt_permissions = mcvirt_config.getPermissionConfig()
        if (self.checkPermissionInConfig(mcvirt_permissions, user_object.getUsername(), permission_enum)):
            return True

        # If a vm_object has been passed, check the VM
        # configuration file for the required permissions
        if (vm_object):
            vm_config_object = vm_object.getConfigObject()
            vm_config = vm_config_object.getPermissionConfig()

            # Determine if the user has been granted the required permissions
            # in the VM configuration file
            if (self.checkPermissionInConfig(vm_config, user_object.getUsername(), permission_enum)):
                return True

        return False

    def checkPermissionInConfig(self, permission_config, user, permission_enum):
        """Reads a permissions config and determines if a user has a given permission"""
        # Ititerate through the permission groups on the VM
        for (permission_group, users) in permission_config.items():

            # Check that the group, defined in the VM, is defined in this class
            if (permission_group not in PERMISSION_GROUPS.keys()):
                raise InvalidPermissionGroupException(
                    'Permissions group, %s, does not exist' % permission_group
                )

            # Check if user is part of the group and the group contains
            # the required permission
            if ((user in users) and
                    (permission_enum in PERMISSION_GROUPS[permission_group])):
                return True

        return False

    def isSuperuser(self):
        """Determines if the current user is a superuser of MCVirt"""
        # Cluster users can do anything
        if self.check_user_type('ClusterUser'):
            return True
        user_object = self.mcvirt_instance.getSessionObject().getProxyUserObject()
        username = user_object.getUsername()
        superusers = self.getSuperusers()

        return ((username in superusers))

    def getSuperusers(self):
        """Returns a list of superusers"""
        mcvirt_config = MCVirtConfig()
        return mcvirt_config.getConfig()['superusers']

    @Pyro4.expose()
    @lockingMethod()
    def addSuperuser(self, user_object, ignore_duplicate=None):
        """Adds a new superuser"""
        from mcvirt.cluster.cluster import Cluster

        # Ensure the user is a superuser
        if (not self.isSuperuser()):
            raise InsufficientPermissionsException(
                'User must be a superuser to manage superusers'
            )
        print user_object
        user_object = self._convert_remote_object(user_object)
        print user_object
        username = user_object.getUsername()
        print username

        mcvirt_config = MCVirtConfig()

        # Ensure user is not already a superuser
        if (username not in self.getSuperusers()):
            def updateConfig(config):
                config['superusers'].append(username)
            mcvirt_config.updateConfig(updateConfig, 'Added superuser \'%s\'' % username)

        elif (not ignore_duplicate):
            raise DuplicatePermissionException(
                'User \'%s\' is already a superuser' % username
            )

    @Pyro4.expose()
    @lockingMethod()
    def deleteSuperuser(self, user_object):
        """Removes a superuser"""
        from mcvirt.cluster.cluster import Cluster

        # Ensure the user is a superuser
        if (not self.isSuperuser()):
            raise InsufficientPermissionsException(
                'User must be a superuser to manage superusers'
            )

        user_object = self._convert_remote_object(user_object)
        username = user_object.getUsername()

        # Ensure user to be removed is a superuser
        if (username not in self.getSuperusers()):
            raise UserNotPresentInGroup('User \'%s\' is not a superuser' % username)

        mcvirt_config = MCVirtConfig()

        def updateConfig(config):
            config['superusers'].remove(username)
        mcvirt_config.updateConfig(updateConfig, 'Removed \'%s\' from superuser group' % username)

        if (self.mcvirt_instance.initialiseNodes()):
            cluster_object = Cluster(self.mcvirt_instance)
            cluster_object.runRemoteCommand('auth-deleteSuperuser',
                                            {'username': username})

    @Pyro4.expose()
    @lockingMethod()
    def addUserPermissionGroup(self, permission_group, user_object,
                               vm_object=None, ignore_duplicate=False):
        """Adds a user to a permissions group on a VM object"""
        from mcvirt.cluster.cluster import Cluster

        # Check if user running script is able to add users to permission group
        if not (self.isSuperuser() or
                (vm_object and self.assertPermission(PERMISSIONS.MANAGE_VM_USERS,
                                                     vm_object) and
                 permission_group == 'user')):
            raise InsufficientPermissionsException('VM owners cannot add manager other owners')

        user_object = self._convert_remote_object(user_object)
        vm_object = self._convert_remote_object(vm_object) if vm_object is not None else None
        username = user_object.getUsername()

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

            if (self.mcvirt_instance.initialiseNodes()):
                cluster_object = Cluster(self.mcvirt_instance)
                if (vm_object):
                    vm_name = vm_object.getName()
                else:
                    vm_name = None
                cluster_object.runRemoteCommand('auth-addUserPermissionGroup',
                                                {'permission_group': permission_group,
                                                 'username': username,
                                                 'vm_name': vm_name})

        elif (not ignore_duplicate):
            raise DuplicatePermissionException(
                'User \'%s\' already in group \'%s\'' % (username, permission_group)
            )

    @Pyro4.expose()
    @lockingMethod()
    def deleteUserPermissionGroup(self, permission_group, user_object, vm_object=None):
        """Removes a user from a permissions group on a VM object"""
        from mcvirt.cluster.cluster import Cluster

        # Check if user running script is able to remove users to permission group
        if not (self.isSuperuser() or
                (self.assertPermission(PERMISSIONS.MANAGE_VM_USERS, vm_object) and
                 permission_group == 'user') and vm_object):
            raise InsufficientPermissionsException('Does not have required permission')

        user_object = self._convert_remote_object(user_object)
        vm_object = self._convert_remote_object(vm_object) if vm_object is not None else None
        username = user_object.getUsername()

        # Check if user exists in the group
        if (username not in self.getUsersInPermissionGroup(permission_group, vm_object)):
            raise UserNotPresentInGroup('User \'%s\' not in group \'%s\'' %
                                        (username, permission_group))

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

        if (self.mcvirt_instance.initialiseNodes()):
            cluster_object = Cluster(self.mcvirt_instance)
            cluster_object.runRemoteCommand('auth-deleteUserPermissionGroup',
                                            {'permission_group': permission_group,
                                             'username': username,
                                             'vm_name': vm_name})

    def getPermissionGroups(self):
        """Returns a list of user groups"""
        return PERMISSION_GROUPS.keys()

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
            raise InvalidPermissionGroupException(
                'Permission group \'%s\' does not exist' % permission_group
            )

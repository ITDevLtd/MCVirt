"""Provide permission enum and permission group definitions."""

# Copyright (c) 2016 - I.T. Dev Ltd
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


PERMISSIONS = Enum('PERMISSIONS', ['CHANGE_VM_POWER_STATE', 'CREATE_VM', 'MODIFY_VM',
                                   'MANAGE_VM_USERS', 'VIEW_VNC_CONSOLE', 'CLONE_VM',
                                   'DELETE_CLONE', 'MANAGE_HOST_NETWORKS', 'MANAGE_CLUSTER',
                                   'MANAGE_DRBD', 'CAN_IGNORE_DRBD', 'MIGRATE_VM',
                                   'DUPLICATE_VM', 'SET_VM_LOCK', 'BACKUP_VM',
                                   'CAN_IGNORE_CLUSTER', 'MOVE_VM', 'SET_VM_NODE',
                                   'MANAGE_USERS', 'TEST_SUPERUSER_PERMISSION',
                                   'TEST_OWNER_PERMISSION', 'TEST_USER_PERMISSION',
                                   'SUPERUSER', 'MANAGE_NODE', 'SET_SYNC_STATE',
                                   'MANAGE_ISO', 'MANAGE_STORAGE_BACKEND',
                                   'MANAGE_STORAGE_VOLUME', 'MANAGE_GROUPS',
                                   'MANAGE_GROUP_MEMBERS'])

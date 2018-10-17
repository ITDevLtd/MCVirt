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
                                   'MANAGE_GROUP_MEMBERS', 'MANAGE_GLOBAL_WATCHDOG'])

PERMISSION_DESCRIPTIONS = {
    'CHANGE_VM_POWER_STATE': ('Power on, power off, reset and shutdown (ACPI) '
                              'virtual machine'),
    'CREATE_VM': ('Create a virtual machine and required resources '
                  '(network interface, hard drive etc.)'),
    'MODIFY_VM': ('Modify attributes of a virtual machine '
                  '(e.g. Memory/CPU allocation, CPU flags etc.)'),
    'MANAGE_VM_USERS': 'Add/remove users from a permission group for a specific virtual machine',
    'VIEW_VNC_CONSOLE': 'Obtain VNC port and tunnel VNC connections (in later versions)',
    'CLONE_VM': 'Clone a virtual machine to a new virtual macine',
    'DELETE_CLONE': ('Delete a virtual machine, which was created '
                     'via cloning another virtual machine'),
    'MANAGE_HOST_NETWORKS': 'Create/delete host networks that are mapped to the virtual machine',
    'MANAGE_CLUSTER': 'Add/remove nodes from the cluster',
    'MANAGE_DRBD': 'Enable DRBD functionality in the cluster',
    'CAN_IGNORE_DRBD': 'Ignore DRBD whilst performing virtual machine operations',
    'MIGRATE_VM': 'Perform both online and offline virtual machine migrations between hosts',
    'DUPLICATE_VM': 'Duplicate a virtual machine to a new virtual machine',
    'SET_VM_LOCK': 'Manually lock and unlock virtual machines to stop other operations on it',
    'BACKUP_VM': 'Create a backup of virtual machine hard drives',
    'CAN_IGNORE_CLUSTER': 'Perform other operations whilst ignoring failing nodes',
    'MOVE_VM': 'Move a virtual machine between non-shared storage',
    'MANAGE_USERS': 'Create/delete users',
    'MANAGE_NODE': 'Modify node-specific configurations, such as IP address',
    'MANGAE_ISO': 'Upload and delete ISOs from hosts',
    'MANAGE_STORAGE_BACKEND': 'Create/delete storage backends',
    'MANAGE_GROUPS': 'Create, delete and modify permissions groups',
    'MANAGE_GROUP_MEMBERS': 'Add/remove users from permission groups',
    'MANAGE_GLOBAL_WATCHDOG': 'Manage the global configuration for watchdog'
}

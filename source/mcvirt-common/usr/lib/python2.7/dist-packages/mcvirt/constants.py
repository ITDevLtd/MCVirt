"""Provide constants used throughout MCVirt."""

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

from mcvirt.utils import get_hostname
from enum import Enum


class DirectoryLocation(object):
    """Provides directory/file path constants."""

    TEMPLATE_DIR = '/usr/lib/python2.7/dist-packages/mcvirt/templates'
    OS_CONFIG_DIR = '/etc/mcvirt'
    BASE_STORAGE_DIR = '/var/lib/mcvirt'
    NODE_STORAGE_DIR = BASE_STORAGE_DIR + '/' + get_hostname()
    BASE_VM_STORAGE_DIR = NODE_STORAGE_DIR + '/vm'
    ISO_STORAGE_DIR = NODE_STORAGE_DIR + '/iso'
    LOCK_FILE_DIR = '/var/run/lock/mcvirt'
    LOCK_FILE = LOCK_FILE_DIR + '/lock'
    LOG_FILE = '/var/log/mcvirt.log'
    DRBD_HOOK_CONFIG = NODE_STORAGE_DIR + '/drbd-hook-config.json'


class LockStates(Enum):
    """Library of virtual machine lock states."""

    UNLOCKED = 0
    LOCKED = 1


class PowerStates(Enum):
    """Library of virtual machine power states."""

    STOPPED = 0
    RUNNING = 1
    UNKNOWN = 2


class AutoStartStates(Enum):
    """States that autostart can be"""

    NO_AUTOSTART = 0
    ON_BOOT = 1
    ON_POLL = 2


class AgentSerialConfig(object):
    """Provide static config for agent serial config"""

    # Baud rate
    BAUD_RATE = 115200

    # Agent Port
    AGENT_PORT = "ttyS0"
    AGENT_PORT_PATH = "/dev/%s" % AGENT_PORT


# Name of the default storage backend, used during upgrade
# from pre-v9.0.0 installations
DEFAULT_STORAGE_NAME = 'default'
DEFAULT_STORAGE_ID = 'sb-1625cdb75d25d9f6-31bca02094eb78126a517b20'

# Name of the default network, which is created by libvirt
DEFAULT_LIBVIRT_NETWORK_NAME = 'default'

DEFAULT_USER_GROUP_ID = 'gp-b14361404c078ffd54-31bca02094eb78126a517b'
DEFAULT_OWNER_GROUP_ID = 'gp-ef31a4aef108265dca-31bca02094eb78126a517b'
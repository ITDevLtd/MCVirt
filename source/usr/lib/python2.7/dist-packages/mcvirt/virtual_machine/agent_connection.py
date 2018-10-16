"""Module for handling agent connection"""
# Copyright (c) 2018 - I.T. Dev Ltd
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

import time
from threading import Lock, Condition
from serial import Serial

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.exceptions import TimoutExceededSerialLockError


class AgentConnection(PyroObject):
    """Obtain connection and perform commands with VM agent"""

    LOCKS = {}
    COND = {}
    LOCK_TIMEOUT = 5

    def __init__(self, virtual_machine):
        """Store member variables"""
        self.virtual_machine = virtual_machine

    def get_lock_condition(self):
        """Return lock object for VM"""
        cache_key = self.virtual_machine.get_name()

        # Create lock if it does not exist for VM
        if cache_key not in AgentConnection.LOCKS:
            AgentConnection.LOCKS[cache_key] = Lock()

        # Create condition if it does not exist for VM
        if cache_key not in AgentConnection.COND:
            AgentConnection.COND[cache_key] = Condition(AgentConnection.LOCKS[cache_key])

        return AgentConnection.LOCKS[cache_key], \
            AgentConnection.COND[cache_key]

    def wait_lock(self, callback):
        """Wait for lock"""
        lock, cond = self.get_lock_condition()
        with cond:
            current_time = start_time = time.time()
            while current_time < start_time + self.LOCK_TIMEOUT:
                if lock.acquire(False):
                    return callback()
                else:
                    cond.wait(self.LOCK_TIMEOUT - current_time + start_time)
                    current_time = time.time()
        raise TimoutExceededSerialLockError('Timeout exceeded whilst waiting for serial lock')

    def get_serial_connection(self):
        """Obtain serial connection object"""
        pass

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
from mcvirt.exceptions import TimeoutExceededSerialLockError
from mcvirt.constants import AgentSerialConfig


class AgentConnection(PyroObject):
    """Obtain connection and perform commands with VM agent"""

    LOCKS = {}
    LOCK_TIMEOUT = 2

    def __init__(self, virtual_machine):
        """Store member variables"""
        self.virtual_machine = virtual_machine

    def get_lock_condition(self):
        """Return lock object for VM"""
        cache_key = self.virtual_machine.get_name()

        # Create lock if it does not exist for VM
        if cache_key not in AgentConnection.LOCKS:
            AgentConnection.LOCKS[cache_key] = LockObject()

        return AgentConnection.LOCKS[cache_key]

    def wait_lock(self, callback):
        """Wait for lock"""
        # @TODO Replace with 'with' statement
        # Get lock and condition object
        lock = self.get_lock_condition()
        with TimeoutLock(lock=lock, timeout=AgentConnection.LOCK_TIMEOUT):
            # Attempt to run callback method and capture output
            conn = None
            # Obtain serial connection and
            # pass to callback
            conn = self.get_serial_connection()
            try:
                resp = callback(conn)
            except Exception:
                conn.close()
                raise
            conn.close()
            return resp

    def get_serial_connection(self):
        """Obtain serial connection object"""
        serial_port = self.virtual_machine.get_host_agent_path()
        timeout = self.virtual_machine.get_agent_timeout()
        serial_obj = Serial(port=serial_port,
                            baudrate=AgentSerialConfig.BAUD_RATE,
                            timeout=timeout,
                            rtscts=True, dsrdtr=True)

        # Attempt to clear buffers, but retain compatibility with
        # older versions
        if 'reset_input_buffer' in dir(serial_obj):
            serial_obj.reset_input_buffer()
        if 'reset_output_buffer' in dir(serial_obj):
            serial_obj.reset_output_buffer()
        return serial_obj


class LockObject(object):
    """Lock object for timeout locks"""

    def __init__(self):
        """Create lock and condition objects"""
        self.lock = Lock()
        self.cond = Condition()

    def release(self):
        """Release lock and notify the condition"""
        self.lock.release()
        with self.cond:
            self.cond.notify()


class TimeoutLock(object):
    """Provide lock functionality with a timeout"""

    def __init__(self, lock, timeout):
        """Store member variables"""
        self.lock = lock
        self.timeout = timeout

    def __enter__(self):
        """Once entered a 'with' clause"""
        self.acquire()
        return self

    def __exit__(self, type, value, tb):
        """Release lock when exiting 'with' clause and did not raise an exception"""
        self.release()

    def acquire(self):
        """Attempt ot aquire lock"""
        if not self._waitLock():
            raise TimeoutExceededSerialLockError(
                'Timeout exceeded whilst waiting for serial lock')

    def release(self):
        """Release lock object"""
        self.lock.release()

    def _waitLock(self):
        """Loop until either getting lock or timeout exceeded"""
        with self.lock.cond:
            current_time = start_time = time.time()
            while current_time < start_time + self.timeout:
                if self.lock.lock.acquire(False):
                    return True
                else:
                    self.lock.cond.wait(self.timeout - current_time + start_time)
                    current_time = time.time()
        return False

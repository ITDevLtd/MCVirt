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
        # @TODO Replace with 'with' statement
        # Get lock and condition object
        lock, cond = self.get_lock_condition()
        with cond:
            # Get current time
            current_time = start_time = time.time()

            # Whilst timeout has not been exceeded...
            while current_time < start_time + self.LOCK_TIMEOUT:
                # Attempt to aquire lock
                if lock.acquire(False):
                    # Attempt to run callback method and capture output
                    conn = None
                    try:
                        # Obtain serial connection and
                        # pass to callback
                        conn = self.get_serial_connection()
                        resp = callback(conn)
                        conn.close()
                    except:
                        # Release lock and re-raise exception
                        try:
                            conn.close()
                        except:
                            pass
                        lock.release()
                        raise
                    # Release lock and return value
                    conn.close()
                    lock.release()
                    return resp
                else:
                    cond.wait(self.LOCK_TIMEOUT - current_time + start_time)
                    current_time = time.time()

        # If function has not run, raise exception as tieout has been
        # exceeded
        raise TimeoutExceededSerialLockError(
            'Timeout exceeded whilst waiting for serial lock')

    def get_serial_connection(self):
        """Obtain serial connection object"""
        serial_port = self.virtual_machine.get_host_agent_path()
        timeout = self.virtual_machine.get_agent_timeout()
        serial_obj = Serial(port=serial_port,
                            baudrate=AgentSerialConfig.BAUD_RATE,
                            timeout=timeout)

        # Clear buffers and return serial object
        serial_obj.reset_input_buffer()
        serial_obj.reset_output_buffer()
        return serial_obj

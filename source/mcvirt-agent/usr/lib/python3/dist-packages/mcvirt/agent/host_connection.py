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
import json
from serial import Serial

from mcvirt.constants import AgentSerialConfig
from mcvirt.os_stats import OSStats
from mcvirt.version import VERSION


class HostConnection(object):
    """Provide loop that connects to host and runs commands."""

    def start_loop(self):
        """Obtain serial connection and start receiving loop."""
        conn = Serial(port=AgentSerialConfig.AGENT_PORT_PATH,
                      baudrate=AgentSerialConfig.BAUD_RATE,
                      timeout=0,
                      rtscts=True, dsrdtr=True)

        # Attempt to clear buffers, but retain compatibility with
        # older versions
        if 'reset_input_buffer' in dir(conn):
            conn.reset_input_buffer()
        if 'reset_output_buffer' in dir(conn):
            conn.reset_output_buffer()

        while True:
            msg = conn.readline().strip()
            self._handle_command(conn, msg)
            time.sleep(1)

    def _handle_command(self, conn, msg):
        """Proces command from host."""
        # Response to ping
        if msg == 'ping':
            conn.write('pong\n')

        # Obtain CPU and memory stats
        elif msg == 'stats':
            conn.write(json.dumps({
                'cpu_usage': OSStats.get_cpu_usage(),
                'memory_usage': OSStats.get_ram_usage()
            }) + '\n')
        # Return JSON file
        elif msg == 'version':
            conn.write(VERSION + '\n')

        elif msg:
            # Default to outputting %%
            conn.write('%%%%\n')

        conn.flush()

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

from Pyro4 import naming
import threading
import time

class NameServer(threading.Thread):
    """Thread for running the name server"""

    def run(self):
        """Start the Pyro name server"""
        naming.startNSloop(host='0.0.0.0', port=9090, enableBroadcast=False)

    def obtainConnection(self):
        while 1:
            try:
                ns = naming.locateNS(host='127.0.0.1', port=9090, broadcast=False)
                ns = None
                return
            except:
                # Wait for 1 second for name server to come up
                time.sleep(1)

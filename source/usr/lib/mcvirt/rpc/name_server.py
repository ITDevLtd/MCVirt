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

import Pyro4
import time

from mcvirt.utils import get_hostname
from mcvirt.rpc.ssl_socket import SSLSocket


class NameServer(object):
    """Thread for running the name server"""

    def __init__(self):
        """Perform configuration of Pyro4"""
        Pyro4.config.USE_MSG_WAITALL = False
        Pyro4.config.CREATE_SOCKET_METHOD = SSLSocket.create_ssl_socket
        Pyro4.config.CREATE_BROADCAST_SOCKET_METHOD = SSLSocket.create_broadcast_ssl_socket

    def start(self):
        """Start the Pyro name server"""
        # self.daemon.requestLoop()
        Pyro4.config.USE_MSG_WAITALL = False
        Pyro4.naming.startNSloop(host=get_hostname(), port=9090, enableBroadcast=False)

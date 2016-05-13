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

import ssl
import atexit
import Pyro4
import uuid
import time

from mcvirt.mcvirt import MCVirt
from mcvirt.auth.auth import Auth
from mcvirt.virtual_machine.factory import Factory as VirtualMachineFactory
from mcvirt.iso.factory import Factory as IsoFactory
from mcvirt.node.network.factory import Factory as NetworkFactory
from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from mcvirt.auth.factory import Factory as UserFactory
from mcvirt.auth.session import Session
from mcvirt.cluster.cluster import Cluster
from mcvirt.logger import Logger
from ssl_socket import SSLSocket
from mcvirt.utils import get_hostname


class BaseRpcDaemon(Pyro4.Daemon):
    """Override Pyro daemon to add authentication checks and MCVirt integration"""
    def __init__(self, mcvirt_instance, *args, **kwargs):
        """Override init to set required configuration and create nameserver connection"""
        # Require all methods/classes to be exposed
        # DO NOT CHANGE THIS OPTION!
        Pyro4.config.REQUIRE_EXPOSE = True

        # Perform super method for init of daemon
        super(BaseRpcDaemon, self).__init__(*args, **kwargs)

        # Store MCVirt instance
        self.mcvirt_instance = mcvirt_instance
        atexit.register(self.destroy)

    def destroy(self):
        # Create MCVirt instance
        self.mcvirt_instance = None

    def validateHandshake(self, conn, data):
        """Perform authentication on new connections"""
        # Reset session_id for current context
        Pyro4.current_context.session_id = None
        Pyro4.current_context.username = None
        Pyro4.current_context.user_for = None

        # Check and store username from connection
        if 'USER' not in data:
            raise Pyro4.errors.SecurityError('Username and password or Session must be passed')
        username = str(data['USER'])

        # If a password has been provided
        if 'PASS' in data:
            # Store the password and perform authentication check
            password = str(data['PASS'])
            session_object = Session(self.mcvirt_instance)
            session_id = session_object.authenticateUser(username=username, password=password)
            if session_id:
                Pyro4.current_context.username = username
                Pyro4.current_context.session_id = session_id
                if 'ALTU' in data:
                    Pyro4.current_context.user_for = data['ALTU']
                return session_id

        # If a session id has been passed, store it and check the session_id/username against active sessions
        elif 'SEID' in data:
            session_id = str(data['SEID'])
            session_object = Session(self.mcvirt_instance)
            if session_object.authenticateSession(username=username, session=session_id):
                Pyro4.current_context.username = username
                Pyro4.current_context.session_id = session_id
                if 'ALTU' in data:
                    Pyro4.current_context.user_for = data['ALTU']
                return session_id

        # If no valid authentication was provided, raise an error
        raise Pyro4.errors.SecurityError('Invalid username/password/session')


class DaemonSession(object):
    @Pyro4.expose()
    def getSessionId(self):
        if Pyro4.current_context.session_id:
            return Pyro4.current_context.session_id
        else:
            raise error.DaemonError('No Session ID')


class RpcNSMixinDaemon(object):
    """Wrapper for the daemon. Required since the
       Pyro daemon class overrides get/setattr and other
       built-in object methods"""

    def __init__(self):
        """Store required object member variables and create MCVirt object"""
        # Store nameserver, MCVirt instance and create daemon
        self.mcvirt_instance = MCVirt()
        atexit.register(self.destroy)

        Pyro4.config.USE_MSG_WAITALL = False
        Pyro4.config.CREATE_SOCKET_METHOD = SSLSocket.create_ssl_socket
        Pyro4.config.CREATE_BROADCAST_SOCKET_METHOD = SSLSocket.create_broadcast_ssl_socket
        self.hostname = get_hostname()

        # Wait for nameserver
        self.obtainConnection()

        self.daemon = BaseRpcDaemon(mcvirt_instance=self.mcvirt_instance)
        self.registerFactories()

    def start(self):
        """Start the Pyro daemon"""
        self.daemon.requestLoop()

    def register(self, obj_or_class, objectId, *args, **kwargs):
        """Override register to register object with NS"""
        uri = self.daemon.register(obj_or_class, *args, **kwargs)
        ns = Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
        ns.register(objectId, uri)
        ns = None
        return uri

    def registerFactories(self):
        """Register base MCVirt factories with RPC daemon"""
        # Register session class
        self.register(DaemonSession, objectId='session', force=True)

        # Create Virtual machine factory object and register with daemon
        virtual_machine_factory = VirtualMachineFactory(self.mcvirt_instance)
        self.register(virtual_machine_factory, objectId='virtual_machine_factory', force=True)

        # Create network factory object and register with daemon
        network_factory = NetworkFactory(self.mcvirt_instance)
        self.register(network_factory, objectId='network_factory', force=True)

        # Create network factory object and register with daemon
        hard_drive_factory = HardDriveFactory(self.mcvirt_instance)
        self.register(hard_drive_factory, objectId='hard_drive_factory', force=True)

        # Create ISO factory object and register with daemon
        iso_factory = IsoFactory(self.mcvirt_instance)
        self.register(iso_factory, objectId='iso_factory', force=True)

        # Create auth object and register with daemon
        auth = Auth(self.mcvirt_instance)
        self.register(auth, objectId='auth', force=True)

        # Create user factory object and register with Daemon
        user_factory = UserFactory(self.mcvirt_instance)
        self.register(user_factory, objectId='user_factory', force=True)

        # Create cluster object and register with Daemon
        cluster = Cluster(self.mcvirt_instance)
        self.register(cluster, objectId='cluster', force=True)

        # Create logger object and register with daemon
        logger = Logger()
        self.register(logger, objectId='logger', force=True)

    def destroy(self):
        """Destroy the MCVirt instance on destruction of object"""
        # Create MCVirt instance
        self.mcvirt_instance = None

    def obtainConnection(self):
        while 1:
            try:
                Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
                return
            except Exception as e:
                # Wait for 1 second for name server to come up
                time.sleep(1)

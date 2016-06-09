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
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.virtual_machine.factory import Factory as VirtualMachineFactory
from mcvirt.iso.factory import Factory as IsoFactory
from mcvirt.node.network.factory import Factory as NetworkFactory
from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from mcvirt.auth.factory import Factory as UserFactory
from mcvirt.auth.session import Session
from mcvirt.cluster.cluster import Cluster
from mcvirt.virtual_machine.network_adapter.factory import Factory as NetworkAdapterFactory
from mcvirt.logger import Logger
from mcvirt.node.drbd import DRBD as NodeDRBD
from mcvirt.node.node import Node
from ssl_socket import SSLSocket
from mcvirt.utils import get_hostname
from constants import Annotations


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
        self.registered_factories = {}
        atexit.register(self.destroy)

    def destroy(self):
        """Remove references to objects"""
        for factory in self.registered_factories:
            self.registered_factories[factory] = None
        # Create MCVirt instance
        self.mcvirt_instance = None

    def validateHandshake(self, conn, data):
        """Perform authentication on new connections"""
        # Reset session_id for current context
        Pyro4.current_context.session_id = None
        Pyro4.current_context.username = None
        Pyro4.current_context.proxy_user = None
        Pyro4.current_context.has_lock = False
        Pyro4.current_context.cluster_master = True

        # Check and store username from connection
        if Annotations.USERNAME not in data:
            raise Pyro4.errors.SecurityError('Username and password or Session must be passed')
        username = str(data[Annotations.USERNAME])

        # If a password has been provided
        try:
            if Annotations.PASSWORD in data:
                # Store the password and perform authentication check
                password = str(data[Annotations.PASSWORD])
                session_instance = Session(self.mcvirt_instance)
                session_id = session_instance.authenticateUser(username=username, password=password)
                if session_id:
                    Pyro4.current_context.username = username
                    Pyro4.current_context.session_id = session_id

                    # If the authenticated user can specify a proxy user, and a proxy user
                    # has been specified, set this in the current context
                    user_object = session_instance.getCurrentUserObject()
                    if user_object.ALLOW_PROXY_USER and Annotations.PROXY_USER in data:
                        Pyro4.current_context.proxy_user = data[Annotations.PROXY_USER]

                    # If the user is a cluster/connection user, treat this connection
                    # as a cluster client (the command as been executed on a remote node)
                    # unless specified otherwise
                    auth = self.registered_factories['auth']
                    if user_object.CLUSTER_USER:
                        if user_object.CLUSTER_USER and Annotations.CLUSTER_MASTER in data:
                            Pyro4.current_context.cluster_master = data[Annotations.CLUSTER_MASTER]
                        else:
                            Pyro4.current_context.cluster_master = False
                    else:
                        Pyro4.current_context.cluster_master = True

                    if user_object.CLUSTER_USER and Annotations.HAS_LOCK in data:
                        Pyro4.current_context.has_lock = data[Annotations.HAS_LOCK]
                    else:
                        Pyro4.current_context.has_lock = False

                    if (auth.checkPermission(PERMISSIONS.CAN_IGNORE_CLUSTER, user_object=user_object)
                            and Annotations.IGNORE_CLUSTER in data):
                        Pyro4.current_context.ignore_cluster = data[Annotations.IGNORE_CLUSTER]
                    else:
                        Pyro4.current_context.ignore_cluster = False

                    if (auth.checkPermission(PERMISSIONS.CAN_IGNORE_DRBD, user_object=user_object)
                            and Annotations.IGNORE_DRBD in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_DRBD]
                    else:
                        Pyro4.current_context.ignore_drbd = False

                    return session_id

            # If a session id has been passed, store it and check the session_id/username against active sessions
            elif Annotations.SESSION_ID in data:
                session_id = str(data[Annotations.SESSION_ID])
                session_instance = Session(self.mcvirt_instance)
                if session_instance.authenticateSession(username=username, session=session_id):
                    Pyro4.current_context.username = username
                    Pyro4.current_context.session_id = session_id

                    # Determine if user can provide alternative users
                    user_object = session_instance.getCurrentUserObject()
                    if user_object.ALLOW_PROXY_USER and Annotations.PROXY_USER in data:
                        Pyro4.current_context.proxy_user = data[Annotations.PROXY_USER]

                    # If the user is a cluster/connection user, treat this connection
                    # as a cluster client (the command as been executed on a remote node)
                    # unless specified otherwise
                    auth = self.registered_factories['auth']
                    if user_object.CLUSTER_USER:
                        if user_object.CLUSTER_USER and Annotations.CLUSTER_MASTER in data:
                            Pyro4.current_context.cluster_master = data[Annotations.CLUSTER_MASTER]
                        else:
                            Pyro4.current_context.cluster_master = False
                    else:
                        Pyro4.current_context.cluster_master = True

                    if user_object.CLUSTER_USER and Annotations.HAS_LOCK in data:
                        Pyro4.current_context.has_lock = data[Annotations.HAS_LOCK]
                    else:
                        Pyro4.current_context.has_lock = False

                    if (auth.checkPermission(PERMISSIONS.CAN_IGNORE_CLUSTER, user_object=user_object)
                            and Annotations.IGNORE_CLUSTER in data):
                        Pyro4.current_context.ignore_cluster = data[Annotations.IGNORE_CLUSTER]
                    else:
                        Pyro4.current_context.ignore_cluster = False

                    if (auth.checkPermission(PERMISSIONS.CAN_IGNORE_DRBD, user_object=user_object)
                            and Annotations.IGNORE_DRBD in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_DRBD]
                    else:
                        Pyro4.current_context.ignore_drbd = False

                    return session_id
        except Exception, e:
            print str(e)
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

        self.daemon = BaseRpcDaemon(mcvirt_instance=self.mcvirt_instance,
                                    host=self.hostname)
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
        self.daemon.registered_factories[objectId] = obj_or_class
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

        # Create node DRBD object and register with daemon
        node_drbd = NodeDRBD(self.mcvirt_instance)
        self.register(node_drbd, objectId='node_drbd', force=True)

        # Create network adapter factory and register with daemon
        network_adapter_factory = NetworkAdapterFactory(self.mcvirt_instance)
        self.register(network_adapter_factory, objectId='network_adapter_factory', force=True)

        # Create node instance and register with daemon
        node = Node(self.mcvirt_instance)
        self.register(node, objectId='node', force=True)

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

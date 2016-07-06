"""Provide class for RPC daemon."""

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

import atexit
import Pyro4
import time

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
from mcvirt.node.drbd import Drbd as NodeDrbd
from mcvirt.node.node import Node
from mcvirt.rpc.ssl_socket import SSLSocket
from mcvirt.rpc.certificate_generator_factory import CertificateGeneratorFactory
from mcvirt.node.libvirt_config import LibvirtConfig
from mcvirt.libvirt_connector import LibvirtConnector
from mcvirt.utils import get_hostname
from mcvirt.rpc.constants import Annotations
from mcvirt.rpc.daemon_lock import DaemonLock


class BaseRpcDaemon(Pyro4.Daemon):
    """Override Pyro daemon to add authentication checks and MCVirt integration"""

    def __init__(self, *args, **kwargs):
        """Override init to set required configuration and create nameserver connection"""
        # Require all methods/classes to be exposed
        # DO NOT CHANGE THIS OPTION!
        Pyro4.config.REQUIRE_EXPOSE = True

        # Perform super method for init of daemon
        super(BaseRpcDaemon, self).__init__(*args, **kwargs)

        # Store MCVirt instance
        self.registered_factories = {}
        atexit.register(self.destroy)

    def destroy(self):
        """Remove references to objects"""
        for factory in self.registered_factories:
            self.registered_factories[factory] = None

    def validateHandshake(self, conn, data):  # Override name of upstream method # noqa
        """Perform authentication on new connections"""
        # Reset session_id for current context
        Pyro4.current_context.STARTUP_PERIOD = False
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
            # @TODO - Re-factor as the logic below is duplicated for SESSION_ID in data clause
            if Annotations.PASSWORD in data:
                # Store the password and perform authentication check
                password = str(data[Annotations.PASSWORD])
                session_instance = self.registered_factories['mcvirt_session']
                session_id = session_instance.authenticate_user(username=username,
                                                                password=password)
                if session_id:
                    Pyro4.current_context.username = username
                    Pyro4.current_context.session_id = session_id

                    # If the authenticated user can specify a proxy user, and a proxy user
                    # has been specified, set this in the current context
                    user_object = session_instance.get_current_user_object()
                    if user_object.allow_proxy_user and Annotations.PROXY_USER in data:
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

                    if (auth.check_permission(PERMISSIONS.CAN_IGNORE_CLUSTER,
                                              user_object=user_object) and
                            Annotations.IGNORE_CLUSTER in data):
                        Pyro4.current_context.ignore_cluster = data[Annotations.IGNORE_CLUSTER]
                    else:
                        Pyro4.current_context.ignore_cluster = False

                    if (auth.check_permission(PERMISSIONS.CAN_IGNORE_DRBD,
                                              user_object=user_object) and
                            Annotations.IGNORE_Drbd in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_Drbd]
                    else:
                        Pyro4.current_context.ignore_drbd = False
                    if Pyro4.current_context.cluster_master:
                        self.registered_factories['cluster'].check_node_versions()
                    return session_id

            # If a session id has been passed, store it and check the
            # session_id/username against active sessions
            elif Annotations.SESSION_ID in data:
                session_id = str(data[Annotations.SESSION_ID])
                session_instance = self.registered_factories['mcvirt_session']
                if session_instance.authenticate_session(username=username, session=session_id):
                    Pyro4.current_context.username = username
                    Pyro4.current_context.session_id = session_id

                    # Determine if user can provide alternative users
                    user_object = session_instance.get_current_user_object()
                    if user_object.allow_proxy_user and Annotations.PROXY_USER in data:
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

                    if (auth.check_permission(PERMISSIONS.CAN_IGNORE_CLUSTER,
                                              user_object=user_object) and
                            Annotations.IGNORE_CLUSTER in data):
                        Pyro4.current_context.ignore_cluster = data[Annotations.IGNORE_CLUSTER]
                    else:
                        Pyro4.current_context.ignore_cluster = False

                    if (auth.check_permission(PERMISSIONS.CAN_IGNORE_DRBD,
                                              user_object=user_object) and
                            Annotations.IGNORE_Drbd in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_Drbd]
                    else:
                        Pyro4.current_context.ignore_drbd = False

                    if Pyro4.current_context.cluster_master:
                        self.registered_factories['cluster'].check_node_versions()
                    return session_id
        except Pyro4.errors.SecurityError:
            raise
        except Exception, e:
            print str(e)
        # If no valid authentication was provided, raise an error
        raise Pyro4.errors.SecurityError('Invalid username/password/session')


class DaemonSession(object):
    """Class for allowing client to obtain the session ID"""

    @Pyro4.expose()
    def get_session_id(self):
        """Return the client's current session ID"""
        if Pyro4.current_context.session_id:
            return Pyro4.current_context.session_id


class RpcNSMixinDaemon(object):
    """Wrapper for the daemon. Required since the
    Pyro daemon class overrides get/setattr and other
    built-in object methods
    """

    DAEMON = None

    def __init__(self):
        """Store required object member variables and create MCVirt object"""
        # Initialise Pyro4 with flag to showing that the daemon is being started
        Pyro4.current_context.STARTUP_PERIOD = True

        # Store nameserver, MCVirt instance and create daemon
        self.daemon_lock = DaemonLock()

        Pyro4.config.USE_MSG_WAITALL = False
        Pyro4.config.CREATE_SOCKET_METHOD = SSLSocket.create_ssl_socket
        Pyro4.config.CREATE_BROADCAST_SOCKET_METHOD = SSLSocket.create_broadcast_ssl_socket
        Pyro4.config.THREADPOOL_ALLOW_QUEUE = True
        Pyro4.config.THREADPOOL_SIZE = 128
        self.hostname = get_hostname()

        # Ensure that the required SSL certificates exist
        ssl_socket = CertificateGeneratorFactory().get_cert_generator('localhost')
        ssl_socket.check_certificates(check_client=False)
        ssl_socket = None

        # Wait for nameserver
        self.obtain_connection()

        RpcNSMixinDaemon.DAEMON = BaseRpcDaemon(host=self.hostname)
        self.register_factories()

        # Ensure libvirt is configured
        cert_gen_factory = RpcNSMixinDaemon.DAEMON.registered_factories[
            'certificate_generator_factory']
        cert_gen = cert_gen_factory.get_cert_generator('localhost')
        cert_gen.check_certificates()
        cert_gen = None
        cert_gen_factory = None

    def start(self, *args, **kwargs):
        """Start the Pyro daemon"""
        Pyro4.current_context.STARTUP_PERIOD = False
        RpcNSMixinDaemon.DAEMON.requestLoop(*args, **kwargs)

    def register(self, obj_or_class, objectId, *args, **kwargs):  # Override upstream # noqa
        """Override register to register object with NS."""
        uri = RpcNSMixinDaemon.DAEMON.register(obj_or_class, *args, **kwargs)
        ns = Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
        ns.register(objectId, uri)
        ns = None
        RpcNSMixinDaemon.DAEMON.registered_factories[objectId] = obj_or_class
        return uri

    def register_factories(self):
        """Register base MCVirt factories with RPC daemon"""
        # Register session class
        self.register(DaemonSession, objectId='session', force=True)

        # Create Virtual machine factory object and register with daemon
        virtual_machine_factory = VirtualMachineFactory()
        self.register(virtual_machine_factory, objectId='virtual_machine_factory', force=True)

        # Create network factory object and register with daemon
        network_factory = NetworkFactory()
        self.register(network_factory, objectId='network_factory', force=True)

        # Create network factory object and register with daemon
        hard_drive_factory = HardDriveFactory()
        self.register(hard_drive_factory, objectId='hard_drive_factory', force=True)

        # Create ISO factory object and register with daemon
        iso_factory = IsoFactory()
        self.register(iso_factory, objectId='iso_factory', force=True)

        # Create auth object and register with daemon
        auth = Auth()
        self.register(auth, objectId='auth', force=True)

        # Create user factory object and register with Daemon
        user_factory = UserFactory()
        self.register(user_factory, objectId='user_factory', force=True)

        # Create cluster object and register with Daemon
        cluster = Cluster()
        self.register(cluster, objectId='cluster', force=True)

        # Create node Drbd object and register with daemon
        node_drbd = NodeDrbd()
        self.register(node_drbd, objectId='node_drbd', force=True)

        # Create network adapter factory and register with daemon
        network_adapter_factory = NetworkAdapterFactory()
        self.register(network_adapter_factory, objectId='network_adapter_factory', force=True)

        # Create node instance and register with daemon
        node = Node()
        self.register(node, objectId='node', force=True)

        # Create logger object and register with daemon
        logger = Logger()
        self.register(logger, objectId='logger', force=True)

        # Create and register SSLSocketFactory object
        certificate_generator_factory = CertificateGeneratorFactory()
        self.register(certificate_generator_factory,
                      objectId='certificate_generator_factory', force=True)

        # Create libvirt config object and register with daemon
        libvirt_config = LibvirtConfig()
        self.register(libvirt_config, objectId='libvirt_config', force=True)

        # Create and register libvirt connector object
        libvirt_connector = LibvirtConnector()
        self.register(libvirt_connector, objectId='libvirt_connector', force=True)

        # Create an MCVirt session
        RpcNSMixinDaemon.DAEMON.registered_factories['mcvirt_session'] = Session()

    def obtain_connection(self):
        """Attempt to obtain a connection to the name server."""
        while 1:
            try:
                Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
                return
            except Exception as e:
                print e
                # Wait for 1 second for name server to come up
                time.sleep(1)

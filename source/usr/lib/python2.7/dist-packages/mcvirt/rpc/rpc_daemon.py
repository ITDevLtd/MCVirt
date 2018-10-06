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
import signal
import types
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
from mcvirt.storage.factory import Factory as StorageFactory
from mcvirt.rpc.ssl_socket import SSLSocket
from mcvirt.rpc.certificate_generator_factory import CertificateGeneratorFactory
from mcvirt.node.libvirt_config import LibvirtConfig
from mcvirt.node.ldap_factory import LdapFactory
from mcvirt.libvirt_connector import LibvirtConnector
from mcvirt.utils import get_hostname, ensure_hostname_consistent
from mcvirt.rpc.constants import Annotations
from mcvirt.syslogger import Syslogger
from mcvirt.rpc.daemon_lock import DaemonLock
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.exceptions import AuthenticationError
from mcvirt.rpc.expose_method import Expose
from mcvirt.thread.auto_start_watchdog import AutoStartWatchdog


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

    def validateHandshake(self, conn, data):  # Override name of upstream method # noqa
        """Perform authentication on new connections"""
        # Reset session_id for current context
        Pyro4.current_context.STARTUP_PERIOD = False
        Pyro4.current_context.INTERNAL_REQUEST = False
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
                        if Annotations.CLUSTER_MASTER in data:
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
                            Annotations.IGNORE_DRBD in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_DRBD]
                    else:
                        Pyro4.current_context.ignore_drbd = False
                    if Pyro4.current_context.cluster_master:
                        self.registered_factories['cluster'].check_node_versions()
                    Pyro4.current_context.PERMISSION_ASSERTED = False
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
                        if Annotations.CLUSTER_MASTER in data:
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
                            Annotations.IGNORE_DRBD in data):
                        Pyro4.current_context.ignore_drbd = data[Annotations.IGNORE_DRBD]
                    else:
                        Pyro4.current_context.ignore_drbd = False

                    if Pyro4.current_context.cluster_master:
                        self.registered_factories['cluster'].check_node_versions()
                    Pyro4.current_context.PERMISSION_ASSERTED = False
                    return session_id
        except Pyro4.errors.SecurityError:
            raise
        except Exception, e:
            Syslogger.logger().exception('Error during authentication: %s' % str(e))
        # If no valid authentication was provided, raise an error
        raise AuthenticationError('Invalid username/password/session')


class RpcNSMixinDaemon(object):
    """Wrapper for the daemon. Required since the
    Pyro daemon class overrides get/setattr and other
    built-in object methods
    """

    DAEMON = None

    def __init__(self):
        """Store required object member variables and create MCVirt object"""
        # Before doing ANYTHING, ensure that the hostname that MCVirt thinks the
        # machine is (i.e. the hostname that the machine was already setup as)
        # matches the current hostname of the machine
        ensure_hostname_consistent()

        # Initialise Pyro4 with flag to showing that the daemon is being started
        Pyro4.current_context.STARTUP_PERIOD = True

        # Store nameserver, MCVirt instance and create daemon
        self.daemon_lock = DaemonLock()
        self.timer_objects = []

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
        Syslogger.logger().debug('Wait for connection to nameserver')
        self.obtain_connection()
        Syslogger.logger().debug('Obtained nameserver connection')

        RpcNSMixinDaemon.DAEMON = BaseRpcDaemon(host=self.hostname)
        self.register_factories()

        # Ensure libvirt is configured
        Syslogger.logger().debug('Start certificate check')
        cert_gen_factory = RpcNSMixinDaemon.DAEMON.registered_factories[
            'certificate_generator_factory']
        cert_gen = cert_gen_factory.get_cert_generator('localhost')
        cert_gen.check_certificates()
        cert_gen = None
        cert_gen_factory = None

        Syslogger.logger().debug('Register atexit')
        atexit.register(self.shutdown, 'atexit', '')
        for sig in (signal.SIGABRT, signal.SIGILL, signal.SIGINT,
                    signal.SIGSEGV, signal.SIGTERM):
            signal.signal(sig, self.shutdown)

        Syslogger.logger().debug('Initialising objects')
        for registered_object in RpcNSMixinDaemon.DAEMON.registered_factories:
            obj = RpcNSMixinDaemon.DAEMON.registered_factories[registered_object]
            if type(obj) is not types.TypeType:  # noqa
                Syslogger.logger().debug('Initialising object %s' % registered_object)
                obj.initialise()

    def start(self, *args, **kwargs):
        """Start the Pyro daemon"""
        Pyro4.current_context.STARTUP_PERIOD = False
        Syslogger.logger().debug('Authentication enabled')
        Syslogger.logger().debug('Obtaining lock')
        with DaemonLock.LOCK:
            Syslogger.logger().debug('Obtained lock')
            Syslogger.logger().debug('Starting daemon request loop')
            RpcNSMixinDaemon.DAEMON.requestLoop(*args, **kwargs)
        Syslogger.logger().debug('Daemon request loop finished')

    def shutdown(self, signum, frame):
        """Shutdown Pyro Daemon"""
        Syslogger.logger().error('Received signal: %s' % signum)
        for timer in self.timer_objects:
            Syslogger.logger().info('Shutting down timer: %s' % timer)
            try:
                timer.timer.cancel()
            except:
                pass
        RpcNSMixinDaemon.DAEMON.shutdown()
        Syslogger.logger().debug('finisehd shutdown')

    def register(self, obj_or_class, objectId, *args, **kwargs):  # Override upstream # noqa
        """Override register to register object with NS."""
        Syslogger.logger().debug('Registering object: %s' % objectId)
        obj_or_class._pyro_server_ref = RpcNSMixinDaemon.DAEMON
        uri = RpcNSMixinDaemon.DAEMON.register(obj_or_class, *args, **kwargs)
        ns = Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
        ns.register(objectId, uri)
        ns = None
        RpcNSMixinDaemon.DAEMON.registered_factories[objectId] = obj_or_class
        return uri

    def register_factories(self):
        """Register base MCVirt factories with RPC daemon"""
        registration_factories = [
            [VirtualMachineFactory(), 'virtual_machine_factory'],
            [NetworkFactory(), 'network_factory'],
            [HardDriveFactory(), 'hard_drive_factory'],
            [IsoFactory(), 'iso_factory'],
            [Auth(), 'auth'],
            [UserFactory(), 'user_factory'],
            [Cluster(), 'cluster'],
            [NodeDrbd(), 'node_drbd'],
            [NetworkAdapterFactory(), 'network_adapter_factory'],
            [Node(), 'node'],
            [StorageFactory(), 'storage_factory'],
            [Logger.get_logger(), 'logger'],
            [CertificateGeneratorFactory(), 'certificate_generator_factory'],
            [LibvirtConfig(), 'libvirt_config'],
            [LibvirtConnector(), 'libvirt_connector'],
            [LdapFactory(), 'ldap_factory'],
            [MCVirtConfig, 'mcvirt_config']
        ]
        for factory_object, name in registration_factories:
            self.register(factory_object, objectId=name, force=True)

        # Create an MCVirt session
        session_object = Session()
        self.register(session_object, objectId='mcvirt_session', force=True)
        Expose.SESSION_OBJECT = session_object

        # Create autostart watchdog object
        autostart_watchdog = AutoStartWatchdog()
        self.timer_objects.append(autostart_watchdog)
        self.register(autostart_watchdog, objectId='autostart_watchdog', force=True)

    def obtain_connection(self):
        """Attempt to obtain a connection to the name server."""
        while 1:
            try:
                Pyro4.naming.locateNS(host=self.hostname, port=9090, broadcast=False)
                return
            except Exception as e:
                Syslogger.logger().warn('Connecting to name server: %s' % str(e))
                # Wait for 1 second for name server to come up
                time.sleep(1)
            Syslogger.logger().debug('Connection to name server complete')
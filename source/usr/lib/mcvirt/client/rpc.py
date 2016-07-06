"""Provide class for connecting to RPC daemon"""

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

import mcvirt.exceptions  # Import necessary for Pyro # noqa
from mcvirt.exceptions import AuthenticationError
from mcvirt.utils import get_hostname
from mcvirt.rpc.ssl_socket import SSLSocket
from mcvirt.rpc.constants import Annotations


class Connection(object):
    """Connection class, providing connections to the Pyro MCVirt daemon"""

    NS_PORT = 9090
    SESSION_OBJECT = 'session'

    def __init__(self, username=None, password=None, session_id=None,
                 host=None, ignore_cluster=False):
        """Store member variables for connecting"""
        # If the host is not provided, default to the local host
        self.__host = host if host is not None else get_hostname()

        Pyro4.config.USE_MSG_WAITALL = False
        Pyro4.config.CREATE_SOCKET_METHOD = SSLSocket.create_ssl_socket
        Pyro4.config.CREATE_BROADCAST_SOCKET_METHOD = SSLSocket.create_broadcast_ssl_socket
        self.__username = username
        self.__ignore_drbd = False
        self.__ignore_cluster = ignore_cluster
        if 'proxy_user' in dir(Pyro4.current_context):
            self.__proxy_username = Pyro4.current_context.proxy_user
        else:
            self.__proxy_username = None

        # Store the passed session_id so that it may be used for the initial connection
        self.__session_id = session_id

        # Perform an initial connection to obtain/verify the session ID
        self.__session_id = self.__get_session(password=password)

    def __get_session(self, password):
        """Obtain a session ID"""
        try:
            # Attempt to obtain a connection and obtain a session ID
            session_object = self.get_connection(object_name=self.SESSION_OBJECT,
                                                 password=password)
            session_id = session_object._pyroHandshake[Annotations.SESSION_ID]
            return session_id
        except Pyro4.errors.CommunicationError, e:
            raise AuthenticationError(str(e))
        except Pyro4.errors.NamingError, e:
            raise mcvirt.exceptions.InaccessibleNodeException(
                'MCVirt nameserver/daemon is not running on node %s' % self.__host
            )

    def _get_auth_obj(self, password=None):
        """Setup annotations for authentication"""
        auth_dict = {
            Annotations.USERNAME: self.__username
        }
        if password:
            auth_dict[Annotations.PASSWORD] = password
        elif self.__session_id:
            auth_dict[Annotations.SESSION_ID] = self.__session_id
        if self.__proxy_username:
            auth_dict[Annotations.PROXY_USER] = self.__proxy_username

        if 'has_lock' in dir(Pyro4.current_context):
            auth_dict[Annotations.HAS_LOCK] = Pyro4.current_context.has_lock

        auth_dict[Annotations.IGNORE_CLUSTER] = self.__ignore_cluster
        if 'ignore_cluster' in dir(Pyro4.current_context):
            auth_dict[Annotations.IGNORE_CLUSTER] |= Pyro4.current_context.ignore_cluster
        auth_dict[Annotations.IGNORE_Drbd] = self.__ignore_drbd
        if 'ignore_drbd' in dir(Pyro4.current_context):
            auth_dict[Annotations.IGNORE_Drbd] |= Pyro4.current_context.ignore_drbd
        return auth_dict

    def get_connection(self, object_name, password=None):
        """Obtain a connection from pyro for a given object"""
        # Obtain a connection to the name server on the localhost
        ns = Pyro4.naming.locateNS(host=self.__host, port=self.NS_PORT, broadcast=False)

        class AuthProxy(Pyro4.Proxy):

            def _pyroValidateHandshake(self, data):  # Override upstream # noqa
                self._pyroHandshake[Annotations.SESSION_ID] = data

        # Create a Proxy object, using the overriden Proxy class and return.
        proxy = AuthProxy(ns.lookup(object_name))
        proxy._pyroHandshake = self._get_auth_obj(password=password)
        proxy._pyroBind()
        return proxy

    def ignore_drbd(self):
        """Set flag to ignore DRBD"""
        self.__ignore_drbd = True

    def ignore_cluster(self):
        """Set flag to ignore cluster"""
        self.__ignore_cluster = True

    def annotate_object(self, object_ref):
        """Add authentication attributes to remote object"""
        object_ref._pyroHandshake = self._get_auth_obj()

    @property
    def session_id(self):
        """Property for the session ID"""
        return self.__session_id

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

from Pyro4 import socketutil
import ssl
from mcvirt.mcvirt_config

class SSLSocket(object):


    # Guide to creating certs (DEV)
    # REMOVE BEFORE RELEASE 4
    #
    # openssl genrsa -des3 -out ${HOSTNAME}-CA.key 2048
    # openssl req -x509 -new -nodes -key ${HOSTNAME}-CA.key -sha256 -days 1024 -out ${HOSTNAME}-CA.pem
    # openssl genrsa -out ${HOSTNAME}.key 2048
    # openssl req -new -key ${HOSTNAME}.key -out ${HOSTNAME}.csr
    # openssl x509 -req -in ${HOSTNAME}.csr -CA ${HOSTNAME}-CA.pem -CAkey ${HOSTNAME}-CA.key -CAcreateserial -out ${HOSTNAME}.crt -days 500 -sha256
    # openssl x509 -in ${HOSTNAME}.crt -out ${HOSTNAME}.pem -outform PEM
    #

    def __init__(self):
        pass

    @staticmethod
    def createSSLSocket(*args, **kwargs):
        socket = socketutil.createSocket(*args, **kwargs)
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        if server_side:
            ssl_kwargs['keyfile'] = '/home/matthew/w/g/MCVirt/test_cert/laptop02.key'
            ssl_kwargs['certfile'] = '/home/matthew/w/g/MCVirt/test_cert/laptop02.pem'
        else:
            ssl_kwargs['cert_reqs'] = cert_reqs=ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = '/home/matthew/w/g/MCVirt/test_cert/rootCA.pem'
        ssl_socket = ssl.wrap_socket(socket, **ssl_kwargs)

        return ssl_socket

    @staticmethod
    def createBroadcastSSLSocket(*args, **kwargs):
        socket = socketutil.createBroadcastSocket(*args, **kwargs)
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        if server_side:
            ssl_kwargs['keyfile'] = '/home/matthew/w/g/MCVirt/test_cert/laptop02.key'
            ssl_kwargs['certfile'] = '/home/matthew/w/g/MCVirt/test_cert/laptop02.pem'
        else:
            ssl_kwargs['cert_reqs'] = cert_reqs=ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = '/home/matthew/w/g/MCVirt/test_cert/rootCA.pem'
        ssl_socket = ssl.wrap_socket(socket, **ssl_kwargs)
        return ssl_socket

class SSLSocket(object):
    def __init__(self, socket):
        self.socket = socket

    def recv(self, buffer_size):
        return self.socket.read(buffer_size)

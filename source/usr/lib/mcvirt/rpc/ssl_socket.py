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
import socket
import os
from binascii import hexlify

from mcvirt.system import System
from mcvirt.mcvirt import MCVirtException
from mcvirt.mcvirt_config import MCVirtConfig


class SSLSocket(object):
    """
    Class for providing SSL socket wrappers for Pyro.
    Since the MCVirt isn't available for 2/3 of the time that this is used (NS and CLI), all methods
    are static and paths are calculated manually. @TODO Fix this in future - create MCVirt config class.
    """

    OPENSSL = '/usr/bin/openssl'

    @staticmethod
    def get_hostname():
        """Returns the hostname of the system"""
        return socket.gethostname()

    @staticmethod
    def get_ssl_directory():
        ssl_dir = '/var/lib/mcvirt/%s/ssl' % SSLSocket.get_hostname()
        if not os.path.isdir(ssl_dir):
            os.mkdir(ssl_dir)
        return ssl_dir

    @staticmethod
    def get_ca_file(server):
        if server == 'localhost' or server == '127.0.0.1':
            server = SSLSocket.get_hostname()
        return os.path.join(SSLSocket.get_ssl_directory(), '%s-CA.pem' % server)

    @staticmethod
    def get_server_certificates():
        MCVirtConfig()
        ssl_directory = SSLSocket.get_ssl_directory()
        hostname = SSLSocket.get_hostname()
        ca_pass = None
        ca_pub = os.path.join(ssl_directory, '%s-CA.pem' % hostname)
        ca_priv = os.path.join(ssl_directory, '%s-CA.key' % hostname)
        ssl_pass = None
        ssl_pub = os.path.join(ssl_directory, '%s.pem' % hostname)
        ssl_priv = os.path.join(ssl_directory, '%s.key' % hostname)

        if not os.path.isfile(SSLSocket.OPENSSL):
            raise Exception('openssl not found: %s' % SSLSocket.OPENSSL)

        # Create private key for CA, if does not exist
        if (not os.path.isfile(ca_priv) or
                not os.path.isfile(ssl_pub) or
                not os.path.isfile(ssl_priv)):
            # Generate random password for private key
            ca_pass = hexlify(os.urandom(64))
            System.runCommand([SSLSocket.OPENSSL, 'genrsa', '-des3', '-passout',
                               'pass:%s' % ca_pass, '-out', ca_priv, '2048'])
            # Generate public key for CA
            System.runCommand([SSLSocket.OPENSSL, 'req', '-x509', '-new', '-nodes', '-key', ca_priv,
                               '-sha256', '-days', '10240', '-out', ca_pub, '-passin', 'pass:%s' % ca_pass,
                               '-subj', '/C=/ST=/L=/O=MCVirt CA/CN=server'])
            # Generate new SSL private key
            System.runCommand([SSLSocket.OPENSSL, 'genrsa', '-out', ssl_priv, '2048'])

            # Generate certificate request
            ssl_csr = os.path.join(ssl_directory, '%s.csr' % hostname)
            System.runCommand([SSLSocket.OPENSSL, 'req', '-new', '-key', ssl_priv, '-out', ssl_csr,
                               '-subj', '/C=/ST=/L=/O=MCVirt/CN=server'])

            # Generate public key
            System.runCommand([SSLSocket.OPENSSL, 'x509', '-req', '-in', ssl_csr, '-CA', ca_pub,
                               '-CAkey', ca_priv, '-CAcreateserial', '-passin', 'pass:%s' % ca_pass,
                               '-out', ssl_pub, '-outform', 'PEM', '-days', '10240', '-sha256'])
        return ssl_pub, ssl_priv

    @staticmethod
    def create_ssl_socket(*args, **kwargs):
        socket = socketutil.createSocket(*args, **kwargs)
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        if server_side:
            certfile, priv_file = SSLSocket.get_server_certificates()
            ssl_kwargs['keyfile'] = priv_file
            ssl_kwargs['certfile'] = certfile
        else:
            ssl_kwargs['cert_reqs'] = cert_reqs=ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = SSLSocket.get_ca_file(kwargs['connect'][0])

        ssl_socket = ssl.wrap_socket(socket, **ssl_kwargs)
        return ssl_socket

    @staticmethod
    def create_broadcast_ssl_socket(*args, **kwargs):
        socket = socketutil.createBroadcastSocket(*args, **kwargs)
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        if server_side:
            certfile, priv_file = SSLSocket.get_server_certificates()
            ssl_kwargs['keyfile'] = priv_file
            ssl_kwargs['certfile'] = certfile
        else:
            ssl_kwargs['cert_reqs'] = cert_reqs=ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = SSLSocket.get_ca_file(kwargs['connect'][0])
        ssl_socket = ssl.wrap_socket(socket, **ssl_kwargs)
        return ssl_socket

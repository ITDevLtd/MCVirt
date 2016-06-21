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
import Pyro4
import ssl
import socket
import os
from binascii import hexlify

from mcvirt.utils import get_hostname
from mcvirt.system import System
from mcvirt.exceptions import (CACertificateNotFoundException, OpenSSLNotFoundException,
                               CACertificateAlreadyExists, MustGenerateCertificateException)
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.rpc.pyro_object import PyroObject


class Factory(PyroObject):

    @Pyro4.expose
    def get_ssl_socket(self, node):
        ssl_socket = SSLSocket(node)
        self._register_object(ssl_socket)
        return ssl_socket


class SSLSocket(PyroObject):
    """
    Class for providing SSL socket wrappers for Pyro.
    Since the MCVirt isn't available for 2/3 of the time that this is used (NS and CLI), all methods
    are static and paths are calculated manually. @TODO Fix this in future - create MCVirt config class.
    """

    OPENSSL = '/usr/bin/openssl'

    def __init__(self, server=None):
        if not os.path.isfile(self.OPENSSL):
            raise OpenSSLNotFoundException('openssl not found: %s' % self.OPENSSL)

        MCVirtConfig()

        if server == 'localhost' or server == '127.0.0.1' or server is None:
            self.server = get_hostname()
        else:
            self.server = server

    @property
    def IS_LOCAL(self):
        return (self.server == get_hostname())

    @property
    def SSL_DN(self):
        return '/C=/ST=/L=/O=MCVirt/CN=%s' % self.server

    @property
    def SSL_DIRECTORY(self):
        path = '%s/%s' % (self.SSL_BASE_DIRECTORY, self.server)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def SSL_BASE_DIRECTORY(self):
        path = '/var/lib/mcvirt/%s/ssl' % get_hostname()
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def REMOTE_SSL_BASE_DIRECTORY(self):
        path = os.path.join(self.SSL_DIRECTORY, 'remote')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def CA_KEY_FILE(self):
        if not self.IS_LOCAL:
            raise CACertificateNotFoundException('CA key file not available for remote node')
        path = self._get_certificate_path('capriv.pem')

        if not self._ensure_exists(path, assert_raise=False):
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])

        return path

    @property
    def CA_PUB_FILE(self):
        if self.IS_LOCAL:
            base_directory = '/etc/mcvirt'
        else:
            base_directory = self.SSL_DIRECTORY

        path = self._get_certificate_path('cacert.pem',
                                          base_dir=base_directory)

        if not self._ensure_exists(path, assert_raise=False) and self.IS_LOCAL:
            # Generate public key for CA
            System.runCommand([self.OPENSSL, 'req', '-x509', '-new', '-nodes', '-key', self.CA_KEY_FILE,
                               '-sha256', '-days', '10240', '-out', path,
                               '-subj', '%s_ca' % self.SSL_DN])

            if self.IS_LOCAL:
                symlink_path = self._get_certificate_path('cacert.pem')
                os.symlink(path, symlink_path)

        return path

    @CA_PUB_FILE.setter
    def CA_PUB_FILE(self, value):
        if self.IS_LOCAL:
            raise MustGenerateCertificateException('Local machine must generate its CA public file')
        self._write_file(self.CA_PUB_FILE, value)

    @property
    def CLIENT_PUB_FILE(self):
        return self._get_certificate_path('clientcert.pem')

    @CLIENT_PUB_FILE.setter
    def CLIENT_PUB_FILE(self, value):
        self._write_file(self.CLIENT_PUB_FILE, value)

    @property
    def CLIENT_KEY_FILE(self):
        if not self.IS_LOCAL:
            raise CACertificateNotFoundException('Client key file not available for remote node')
        path = self._get_certificate_path('clientkey.pem')

        if not self._ensure_exists(path, assert_raise=False):
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])

        return path

    @property
    def CLIENT_CSR(self):
        return self._get_certificate_path('clientcert.csr')

    @property
    def CLIENT_REMOTE_CSR(self):
        return self._get_certificate_path('incoming.csr', base_dir=self.REMOTE_SSL_BASE_DIRECTORY)

    @CLIENT_REMOTE_CSR.setter
    def CLIENT_REMOTE_CSR(self, value):
        self._write_file(self.CLIENT_REMOTE_CSR, value)

    @property
    def DEPLOYED_CLIENT_PUB_FILE(self):
        return self._get_certificate_path('remote_pub.pem', base_dir=self.REMOTE_SSL_BASE_DIRECTORY)

    @property
    def SERVER_PUB_FILE(self):
        if not self.IS_LOCAL:
            raise CACertificateNotFoundException('Server public key not available for remote node')
        path = self._get_certificate_path('servercert.pem')

        if not self._ensure_exists(path, assert_raise=False):
            # Generate certificate request
            ssl_csr = os.path.join(self.SSL_DIRECTORY, '%s.csr' % self.server)
            System.runCommand([self.OPENSSL, 'req', '-new', '-key', self.SERVER_KEY_FILE, '-out', ssl_csr,
                               '-subj', self.SSL_DN])

            # Generate public key
            System.runCommand([self.OPENSSL, 'x509', '-req', '-in', ssl_csr, '-CA', self.CA_PUB_FILE,
                               '-CAkey', self.CA_KEY_FILE, '-CAcreateserial',
                               '-out', path, '-outform', 'PEM', '-days', '10240', '-sha256'])

        return path

    @property
    def SERVER_KEY_FILE(self):
        if not self.IS_LOCAL:
            raise CACertificateNotFoundException('Server key file not available for remote node')
        
        path = self._get_certificate_path('serverkey.pem')
        if not self._ensure_exists(path, assert_raise=False):
            # Generate new SSL private key
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])
        return path

    def _get_certificate_path(self, certname, base_dir=None):
        if base_dir is None:
            base_dir = self.SSL_DIRECTORY
        return os.path.join(base_dir, certname)

    def _ensure_exists(self, certpath, assert_raise=True):
        if not os.path.exists(certpath):
            if assert_raise:
                raise CACertificateNotFoundException(
                    '%s certificate could not be found for %s' % (certpath, self.server)
                )
            return False
        return True

    def _read_file(self, certpath):
        """Obtains the local machine's CA file contents"""
        with open(certpath, 'r') as cert_fh:
            cert_contents = cert_fh.read()
        return cert_contents

    def _write_file(self, certpath, cert_contents):
        with open(certpath, 'w') as cert_fh:
            cert_fh.write(cert_contents)

    def check_certificates(self):
        """Ensures that the required certificates are available
           to start the daemon and connect to the local host"""
        # Ensure that the server certificates exist
        self.SERVER_PUB_FILE

        # Ensure that the client certificate exists
        if not self._ensure_exists(self.CLIENT_PUB_FILE, assert_raise=False):
            csr = self.generate_csr()
            self.sign_csr(csr)

    def generate_csr(self):
        System.runCommand(['openssl', 'req', '-new', '-key', self.CLIENT_KEY_FILE,
                           '-out', self.CLIENT_CSR, '-subj', self.SSL_DN])
        return self._read_file(self.CLIENT_CSR)

    def sign_csr(self, csr):
        local_server = SSLSocket('localhost')
        self.CLIENT_REMOTE_CSR = csr
        System.runCommand(['openssl', 'x509', '-req', '-extensions', 'usr_cert', '-in', self.CLIENT_REMOTE_CSR,
                           '-CA', local_server.CA_PUB_FILE, '-CAkey', local_server.CA_KEY_FILE, '-CAcreateserial',
                           '-out', self.CLIENT_PUB_FILE, '-outform', 'PEM', '-days', '10240', '-sha256'])

    def get_ca_contents(self):
        return self._read_file(self.CA_PUB_FILE)

    @staticmethod
    def wrap_socket(socket_object, *args, **kwargs):
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        if server_side:
            ssl_object = SSLSocket(server='localhost')
            ssl_object.check_certificates()
            ssl_kwargs['keyfile'] = ssl_object.SERVER_KEY_FILE
            ssl_kwargs['certfile'] = ssl_object.SERVER_PUB_FILE
        else:
            ssl_object = SSLSocket(server=kwargs['connect'][0])
            ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = ssl_object.CA_PUB_FILE
        return ssl.wrap_socket(socket_object, **ssl_kwargs)

    @staticmethod
    def create_ssl_socket(*args, **kwargs):
        socket = socketutil.createSocket(*args, **kwargs)
        ssl_socket = SSLSocket.wrap_socket(socket, *args, **kwargs)
        return ssl_socket

    @staticmethod
    def create_broadcast_ssl_socket(*args, **kwargs):
        socket = socketutil.createBroadcastSocket(*args, **kwargs)
        ssl_socket = SSLSocket.wrap_socket(socket, *args, **kwargs)
        return ssl_socket

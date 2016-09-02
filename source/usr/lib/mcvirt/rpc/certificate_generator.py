"""Provides class to generate and manage SSL certificates"""
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

import os
import shutil

from mcvirt.utils import get_hostname
from mcvirt.system import System
from mcvirt.exceptions import (CACertificateNotFoundException, OpenSSLNotFoundException,
                               MustGenerateCertificateException)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.syslogger import Syslogger


class CertificateGenerator(PyroObject):
    """
    Class for providing SSL socket wrappers for Pyro.
    Since the MCVirt isn't available for 2/3 of the time that this is used (NS and CLI),
    all methods are static and paths are calculated manually.
    @TODO Fix this in future - create MCVirt config class.
    """

    OPENSSL = '/usr/bin/openssl'

    def __init__(self, server=None, remote=False):
        """Store member variables and ensure that openSSL is installed"""
        if not os.path.isfile(self.OPENSSL):
            raise OpenSSLNotFoundException('openssl not found: %s' % self.OPENSSL)

        if server == 'localhost' or server.startswith('127.') or server is None:
            self.server = get_hostname()
        else:
            self.server = server
        self.remote = remote

    @property
    def is_local(self):
        """Determine if the server is the local machine"""
        return (self.server == get_hostname())

    @property
    def ssl_dn(self):
        """"Return the certificate DN is openssl argument format."""
        server = get_hostname() if self.remote else self.server
        return '/C=GB/ST=MCVirt/L=MCVirt/O=MCVirt/CN=%s' % server

    @property
    def ssl_subj(self):
        """Return the SSL DN in regular format"""
        server = get_hostname() if self.remote else self.server
        return 'C=GB,ST=MCVirt,L=MCVirt,O=MCVirt,CN=%s' % server

    @property
    def ssl_directory(self):
        """Return the SSL directory for the server"""
        path = '%s/%s' % (self.ssl_base_directory, self.server)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def ssl_base_directory(self):
        """Return the base SSL directory for the node."""
        path = '/var/lib/mcvirt/%s/ssl' % get_hostname()
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def remote_ssl_directory(self):
        """Return the 'remote' subdirectory of server, used for storing certificates that
        are used by a remote server.
        """
        path = os.path.join(self.ssl_directory, 'remote')
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    @property
    def ca_key_file(self):
        """Return/generate the CA prviate key."""
        if not self.is_local:
            raise CACertificateNotFoundException('CA key file not available for remote node')
        path = self._get_certificate_path('capriv.pem')

        if not self._ensure_exists(path, assert_raise=False):
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '4096'])

        return path

    @property
    def ca_pub_file(self):
        """Return/generate the CA pub file"""
        base_dir = '/etc/mcvirt' if self.is_local else None

        path = self._get_certificate_path('cacert.pem',
                                          base_dir=base_dir)

        if not self._ensure_exists(path, assert_raise=False) and self.is_local:
            # Generate public key for CA
            System.runCommand([self.OPENSSL, 'req', '-x509', '-new', '-nodes',
                               '-key', self.ca_key_file, '-sha256', '-days', '10240', '-out', path,
                               '-subj', '%s_ca' % self.ssl_dn])

            if self.is_local:
                symlink_path = self._get_certificate_path('cacert.pem')
                os.symlink(path, symlink_path)

        return path

    @ca_pub_file.setter
    def ca_pub_file(self, value):
        """Write the CA public key contents to the file"""
        if self.is_local:
            raise MustGenerateCertificateException(
                'Local machine must generate its CA public file'
            )
        self._write_file(self.ca_pub_file, value)

    @property
    def client_pub_file(self):
        """Return/generate the client public file, used for connecting to the libvirt daemon"""
        return self._get_certificate_path('clientcert.pem', allow_remote=True)

    @client_pub_file.setter
    def client_pub_file(self, value):
        self._write_file(self.client_pub_file, value)

    @property
    def client_key_file(self):
        """Obtain the private key for the client key"""
        path = self._get_certificate_path('clientkey.pem')

        if not self._ensure_exists(path, assert_raise=False):
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])

        return path

    @property
    def client_csr(self):
        """Return the client CSR"""
        return self._get_certificate_path('clientcert.csr', allow_remote=True)

    @client_csr.setter
    def client_csr(self, value):
        """Write the client CSR"""
        self._write_file(self.client_csr, value)

    @property
    def server_pub_file(self):
        """Obtain the server public key file"""
        if not self.is_local:
            raise CACertificateNotFoundException('Server public key not available for remote node')
        path = self._get_certificate_path('servercert.pem')

        if not self._ensure_exists(path, assert_raise=False):
            # Generate certificate request
            ssl_csr = os.path.join(self.ssl_directory, '%s.csr' % self.server)
            System.runCommand([self.OPENSSL, 'req', '-new', '-key', self.server_key_file,
                               '-out', ssl_csr, '-subj', self.ssl_dn])

            # Generate public key
            System.runCommand([self.OPENSSL, 'x509', '-req', '-in', ssl_csr,
                               '-CA', self.ca_pub_file, '-CAkey', self.ca_key_file,
                               '-CAcreateserial', '-out', path, '-outform', 'PEM',
                               '-days', '10240', '-sha256'])

        return path

    @property
    def server_key_file(self):
        """Obtain the server private key file"""
        if not self.is_local:
            raise CACertificateNotFoundException('Server key file not available for remote node')

        path = self._get_certificate_path('serverkey.pem')
        if not self._ensure_exists(path, assert_raise=False):
            # Generate new SSL private key
            System.runCommand([self.OPENSSL, 'genrsa', '-out', path, '2048'])
        return path

    @property
    def dh_params_file(self):
        """Return the path to the DH parameters file, and create it if it does not exist"""
        if not self.is_local:
            raise CACertificateNotFoundException('DH params file not available for remote node')

        path = self._get_certificate_path('dh_params')
        if not self._ensure_exists(path, assert_raise=False):
            # Generate new DH parameters
            Syslogger.logger().info('Generating DH parameters file')
            System.runCommand([self.OPENSSL, 'dhparam', '-out', path, '2048'])
            Syslogger.logger().info('DH parameters file generated')
        return path

    def _get_certificate_path(self, certname, base_dir=None, allow_remote=False):
        if base_dir is None:
            if allow_remote and self.remote:
                base_dir = self.remote_ssl_directory
            else:
                base_dir = self.ssl_directory

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
        """Obtain the contents of a local certificate"""
        with open(certpath, 'r') as cert_fh:
            cert_contents = cert_fh.read()
        return cert_contents

    def _write_file(self, certpath, cert_contents):
        """Create a local certificate file"""
        with open(certpath, 'w') as cert_fh:
            cert_fh.write(cert_contents)

    def check_certificates(self, check_client=True):
        """Ensure that the required certificates are available
        to start the daemon and connect to the local host
        """
        # Ensure that the server certificates exist
        self.ca_pub_file
        self.server_pub_file

        # Ensure that the client certificate exists
        if check_client and not self._ensure_exists(self.client_pub_file, assert_raise=False):
            cert_gen_factory = self._get_registered_object('certificate_generator_factory')
            local_remote = cert_gen_factory.get_cert_generator('localhost', remote=True)
            csr = self._generate_csr()
            pub_key = local_remote._sign_csr(csr)
            self._add_public_key(pub_key)

    @Expose()
    def generate_csr(self):
        """Generate a certificate request for the remote server"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)
        return self._generate_csr()

    def _generate_csr(self):
        System.runCommand(['openssl', 'req', '-new', '-key', self.client_key_file,
                           '-out', self.client_csr, '-subj', self.ssl_dn])
        return self._read_file(self.client_csr)

    @Expose()
    def sign_csr(self, csr):
        """Sign the CSR for a remote SSL certificate."""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)
        return self._sign_csr(csr)

    def _sign_csr(self, csr):
        self.client_csr = csr
        cert_gen_factory = self._get_registered_object('certificate_generator_factory')
        local_server = cert_gen_factory.get_cert_generator('localhost')
        System.runCommand(['openssl', 'x509', '-req', '-extensions', 'usr_cert',
                           '-in', self.client_csr, '-CA', local_server.ca_pub_file,
                           '-CAkey', local_server.ca_key_file, '-CAcreateserial',
                           '-out', self.client_pub_file, '-outform', 'PEM', '-days', '10240',
                           '-sha256'])

        # Regenerate libvirtd configuration, allowing access to this certificate
        if self.is_local:
            self._get_registered_object('libvirt_config').hard_restart = True
        self._get_registered_object('libvirt_config').generate_config()
        return self._read_file(self.client_pub_file)

    @Expose()
    def remove_certificates(self):
        """Remove a certificate directory for a node"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)
        shutil.rmtree(self.ssl_directory)

    @Expose()
    def add_public_key(self, key):
        """Add the public key for a remote node"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_CLUSTER)
        return self._add_public_key(key)

    def _add_public_key(self, key):
        self.client_pub_file = key

    def get_ca_contents(self):
        """Return the contents of the local CA certificate"""
        return self._read_file(self.ca_pub_file)

"""Provides methods for wrapping Pyro methods with SSL."""
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
from Pyro4 import socketutil
import ssl
import socket

from mcvirt.rpc.certificate_generator_factory import CertificateGeneratorFactory


class SSLSocket(object):
    """Provides methods for wrapping Pyro methods with SSL."""

    CIPHERS = ('ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:' +
               'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:' +
               'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:' +
               'DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:' +
               'ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:' +
               'ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:' +
               'ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:' +
               'DHE-RSA-AES256-SHA256:DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:' +
               'ECDHE-RSA-DES-CBC3-SHA:EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:' +
               'AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS')

    @staticmethod
    def wrap_socket(socket_object, *args, **kwargs):
        """Wrap a Pyro socket connection with SSL."""
        server_side = ('bind' in list(kwargs.keys()))
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'server_side': server_side
        }

        legacy = ('create_default_context' not in dir(ssl))

        # Support old Ubuntu 14.04 machines that have a python version < 2.7.9, which do
        # not support create_default_context in the SSL library
        if legacy:
            ssl_kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1
        else:
            # Create an SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.set_ciphers(SSLSocket.CIPHERS)

        if 'CERTIFICATE_GENERATOR_FACTORY' in dir(Pyro4):
            cert_gen_factory = Pyro4.CERTIFICATE_GENERATOR_FACTORY
        else:
            cert_gen_factory = CertificateGeneratorFactory()
        if server_side:
            cert_gen = cert_gen_factory.get_cert_generator(server='localhost')
            cert_gen.check_certificates(check_client=False)
            if legacy:
                ssl_kwargs['keyfile'] = cert_gen.server_key_file
                ssl_kwargs['certfile'] = cert_gen.server_pub_file
            else:
                ssl_context.load_cert_chain(cert_gen.server_pub_file,
                                            keyfile=cert_gen.server_key_file)
                ssl_context.check_hostname = False
                ssl_context.load_dh_params(cert_gen.dh_params_file)
                ssl_context.verify_mode = ssl.CERT_OPTIONAL
        else:
            # Determine if hostname is an IP address
            try:
                socket.inet_aton(kwargs['connect'][0])
                hostname = socket.gethostbyaddr(kwargs['connect'][0])[0]
            except socket.error:
                hostname = kwargs['connect'][0]

            cert_gen = cert_gen_factory.get_cert_generator(hostname)
            if legacy:
                ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED
                ssl_kwargs['ca_certs'] = cert_gen.ca_pub_file
            else:
                ssl_context.check_hostname = True
                ssl_kwargs['server_hostname'] = hostname
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                ssl_context.load_verify_locations(cafile=cert_gen.ca_pub_file)

        if legacy:
            return ssl.wrap_socket(socket_object, **ssl_kwargs)
        else:
            return ssl_context.wrap_socket(socket_object, **ssl_kwargs)

    @staticmethod
    def create_ssl_socket(*args, **kwargs):
        """Override the Pyro createSocket method and wrap with SSL."""
        socket = socketutil.createSocket(*args, **kwargs)
        ssl_socket = SSLSocket.wrap_socket(socket, *args, **kwargs)
        return ssl_socket

    @staticmethod
    def create_broadcast_ssl_socket(*args, **kwargs):
        """Override the Pyro createBroadcastSocket method and wrap with SSL."""
        socket = socketutil.createBroadcastSocket(*args, **kwargs)
        ssl_socket = SSLSocket.wrap_socket(socket, *args, **kwargs)
        return ssl_socket

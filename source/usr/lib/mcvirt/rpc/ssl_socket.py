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
import socket
import ssl

from mcvirt.rpc.certificate_generator_factory import CertificateGeneratorFactory


class SSLSocket(object):

    @staticmethod
    def wrap_socket(socket_object, *args, **kwargs):
        server_side = ('bind' in kwargs.keys())
        ssl_kwargs = {
            'do_handshake_on_connect': True,
            'ssl_version': ssl.PROTOCOL_SSLv23,
            'server_side': server_side
        }
        cert_gen_factory = CertificateGeneratorFactory()
        if server_side:
            cert_gen = cert_gen_factory.get_cert_generator(server='localhost')
            cert_gen.check_certificates(check_client=False)
            ssl_kwargs['keyfile'] = cert_gen.SERVER_KEY_FILE
            ssl_kwargs['certfile'] = cert_gen.SERVER_PUB_FILE
        else:
            cert_gen = cert_gen_factory.get_cert_generator(kwargs['connect'][0])
            ssl_kwargs['cert_reqs'] = ssl.CERT_REQUIRED
            ssl_kwargs['ca_certs'] = cert_gen.CA_PUB_FILE
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
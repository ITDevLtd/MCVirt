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

import libvirt

from mcvirt.rpc.ssl_socket import SSLSocket
from mcvirt.utils import get_hostname
from mcvirt.rpc.pyro_object import PyroObject


class LibvirtConnector(PyroObject):
    """Obtains/manages Libvirt connections"""

    def get_connection(self, server=None):
        """Obtains a Libvirt connection for a given server"""
        if server is None:
            server = get_hostname()

        ssl_object = self._get_registered_object('certificate_generator_factory').get_cert_generator(server)
        libvirt_url = 'qemu://%s/system?pkipath=%s' % (ssl_object.server, ssl_object.SSL_DIRECTORY)
        connection = libvirt.open(libvirt_url)
        if connection is None:
            raise LibVirtConnectionException(
                'Failed to open connection to the hypervisor on %s' % ssl_object.server
            )
        return connection
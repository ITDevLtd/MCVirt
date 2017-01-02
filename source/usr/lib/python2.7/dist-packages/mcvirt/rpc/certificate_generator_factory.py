"""Provides an interface to obtain certificate generator objects"""
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

from mcvirt.rpc.certificate_generator import CertificateGenerator
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.syslogger import Syslogger


class CertificateGeneratorFactory(PyroObject):
    """Provides an interface to obtain certificate generator objects"""

    CACHED_OBJECTS = {}

    @Expose()
    def get_cert_generator(self, server, remote=False):
        """Obtain a certificate generator object for a given server"""
        if (server, remote) not in CertificateGeneratorFactory.CACHED_OBJECTS:
            cert_generator = CertificateGenerator(server, remote=remote)
            self._register_object(cert_generator)
            if not self._is_pyro_initialised:
                try:
                    Syslogger.logger().info(
                        ('Obtained unregistered version of CertificateGenerator'
                         ' for %s (Remote: %s)') % (server, remote)
                    )
                except:
                    pass
                return cert_generator
            CertificateGeneratorFactory.CACHED_OBJECTS[(server, remote)] = cert_generator

        return CertificateGeneratorFactory.CACHED_OBJECTS[(server, remote)]

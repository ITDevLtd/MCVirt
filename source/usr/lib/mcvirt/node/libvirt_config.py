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

from Cheetah.Template import Template

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname


class LibvirtConfig(PyroObject):
    """Provides configuration for libvirtd"""

    CONFIG_FILE = '/etc/libvirt/libvirtd.conf'
    CONFIG_TEMPLATE = '/usr/lib/mcvirt/templates/libvirtd.conf'
    DEFAULT_FILE = '/etc/default/libvirtd'
    DEFAULT_CONFIG = """
# Defaults for libvirtd initscript (/etc/init.d/libvirtd)
# This is a POSIX shell fragment

# Start libvirtd to handle qemu/kvm:
start_libvirtd="yes"

# options passed to libvirtd, add "-l" to listen on tcp
libvirtd_opts=" --listen --verbose "
"""

    def __init__(self):
        self.hard_restart = False

    def generate_config(self):
        """Generates the libvirtd configuration"""
        libvirt_config = self.get_config()

        # Replace the variables in the template with the local libvirtd configuration
        config_content = Template(file=self.CONFIG_TEMPLATE, searchList=[libvirt_config])

        # Write the libvirt configurations
        with open(self.CONFIG_FILE, 'w') as fh:
            fh.write(config_content.respond())

        with open(self.DEFAULT_FILE, 'w') as default_fh:
            default_fh.write(self.DEFAULT_CONFIG)

        # Update DRBD running configuration
        self._reload_libvirt()

    def get_config(self):
        cert_gen_factory = self._get_registered_object('certificate_generator_factory')
        ssl_socket = cert_gen_factory.get_cert_generator('localhost')
        nodes = self._get_registered_object('cluster').getNodes(return_all=True)
        nodes.append(get_hostname())
        allowed_dns = [cert_gen_factory.get_cert_generator(node).SSL_SUBJ for node in nodes]

        return {
            'ip_address': MCVirtConfig().getListenAddress(),
            'ssl_server_key': ssl_socket.SERVER_KEY_FILE,
            'ssl_server_cert': ssl_socket.SERVER_PUB_FILE,
            'ssl_ca_cert': ssl_socket.CA_PUB_FILE,
            'allowed_nodes': '", "'.join(allowed_dns)
        }

    def _reload_libvirt(self):
        """Forces libvirt to reload it's configuration"""
        action = 'restart' if self.hard_restart else 'force-reload'
        System.runCommand(['service', 'libvirtd', action])
        self.hard_restart = False

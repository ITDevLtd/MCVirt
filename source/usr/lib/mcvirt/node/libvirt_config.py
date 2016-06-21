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


class LibvirtConfig(PyroObject):
    """Provides configuration for libvirtd"""

    CONFIG_FILE = '/etc/libvirt/libvrtd.conf'
    CONFIG_TEMPLATE = '/usr/lib/mcvirt/templates/libvirtd.conf'

    def generate_config(self, initial_run=False):
        """Generates the libvirtd configuration"""
        if initial_run and MCVirtConfig().getConfig()['libvirt_configured']:
            return

        libvirt_config = self.get_config()

        # Replace the variables in the template with the local libvirtd configuration
        config_content = Template(file=self.CONFIG_TEMPLATE, searchList=[libvirt_config])

        # Write the DRBD configuration
        fh = open(self.CONFIG_FILE, 'w')
        fh.write(config_content.respond())
        fh.close()

        # Update DRBD running configuration
        self._reload_libvirt()

        # Update MCVirt config, marking libvirt as having been configured
        if initial_run:
            def updateConfig(config):
                config['libvirt_configured'] = True
            MCVirtConfig().updateConfig(updateConfig, 'Configured libvirtd')

    def get_config(self):
        ssl_socket_factory = self._get_registered_object('ssl_socket_factory')
        ssl_socket = ssl_socket_factory.get_ssl_socket('localhost')
        nodes = self._get_registered_object('cluster').getNodes(return_all=True)
        allowed_dns = [ssl_socket_factory.get_ssl_socket(node).SSL_DN for node in nodes]

        return {
            'ip_address': MCVirtConfig().getListenAddress(),
            'ssl_server_key': ssl_socket.SERVER_KEY_FILE,
            'ssl_server_cert': ssl_socket.SERVER_PUB_FILE,
            'ssl_ca_cert': ssl_socket.CA_PUB_FILE,
            'allowed_nodes': '", "'.join(allowed_dns)
        }

    def _reload_libvirt(self):
        """Forces libvirt to reload it's configuration"""
        System.runCommand(['killall', '-SIGHUP', 'libvirtd'])

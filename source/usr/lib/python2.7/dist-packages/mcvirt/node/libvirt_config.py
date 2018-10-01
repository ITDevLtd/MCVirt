"""Provide class to configure libvirtd"""

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
from Cheetah.Template import Template

from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.system import System
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname
from mcvirt.exceptions import LibvirtNotInstalledException


class LibvirtConfig(PyroObject):
    """Provides configuration for libvirtd"""

    LIBVIRT_USER = 'libvirt-qemu'
    LIBVIRT_GROUP = 'kvm'
    CONFIG_FILE = '/etc/libvirt/libvirtd.conf'
    CONFIG_TEMPLATE = '/usr/lib/python2.7/dist-packages/mcvirt/templates/libvirtd.conf'
    DEFAULT_FILE = '/etc/default/%s'
    DEFAULT_CONFIG = """
# Defaults for libvirtd initscript (/etc/init.d/libvirtd)
# This is a POSIX shell fragment

# Start libvirtd to handle qemu/kvm:
start_libvirtd="yes"

# options passed to libvirtd, add "-l" to listen on tcp
libvirtd_opts=" --listen --verbose %s"
"""

    def __init__(self):
        """Create variable to determine if a hard restart is required"""
        # Determine location of libvirt init script
        self.hard_restart = False
        self.service_name = self.get_service_name()

    def get_service_name(self):
        """Locate the libvirt service"""
        for service_name in ['libvirtd', 'libvirt-bin']:
            if os.path.isfile('/etc/init.d/%s' % service_name):
                return service_name

        raise LibvirtNotInstalledException('Libvirt does not appear to be installed')

    def generate_config(self):
        """Generate the libvirtd configuration"""
        libvirt_config = self.get_config()

        # Replace the variables in the template with the local libvirtd configuration
        config_content = Template(file=self.CONFIG_TEMPLATE, searchList=[libvirt_config])

        # Write the libvirt configurations
        with open(self.CONFIG_FILE, 'w') as fh:
            fh.write(config_content.respond())

        if System.is_running_systemd():
            default_config = self.DEFAULT_CONFIG % ''
        else:
            default_config = self.DEFAULT_CONFIG % '-d '

        with open(self.DEFAULT_FILE % self.service_name, 'w') as default_fh:
            default_fh.write(default_config)

        # Update Drbd running configuration
        self._reload_libvirt()

    def get_config(self):
        """Create the configuration for libvirt"""
        cert_gen_factory = self._get_registered_object('certificate_generator_factory')
        ssl_socket = cert_gen_factory.get_cert_generator('localhost')
        nodes = self._get_registered_object('cluster').get_nodes(return_all=True)
        nodes.append(get_hostname())
        allowed_dns = [cert_gen_factory.get_cert_generator(node).ssl_subj for node in nodes]

        return {
            'ip_address': MCVirtConfig().getListenAddress(),
            'ssl_server_key': ssl_socket.server_key_file,
            'ssl_server_cert': ssl_socket.server_pub_file,
            'ssl_ca_cert': ssl_socket.ca_pub_file,
            'allowed_nodes': '", "'.join(allowed_dns)
        }

    def _reload_libvirt(self):
        """Force libvirt to reload it's configuration"""
        action = 'restart' if self.hard_restart else 'force-reload'
        System.runCommand(['service', self.service_name, action])
        self.hard_restart = False

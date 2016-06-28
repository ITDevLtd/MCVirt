# Copyright (c) 2014 - I.T. Dev Ltd
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

import unittest

from mcvirt.parser import Parser
from mcvirt.node.node import Node
from mcvirt.exceptions import InvalidIPAddressException, InvalidVolumeGroupNameException
from mcvirt.mcvirt_config import MCVirtConfig


class NodeTests(unittest.TestCase):
    """Provides unit tests for the functionality
       provided by the node subparser"""

    @staticmethod
    def suite():
        """Returns a test suite"""
        suite = unittest.TestSuite()
        suite.addTest(NodeTests('test_set_ip_address'))
        suite.addTest(NodeTests('test_set_invalid_ip_address'))
        suite.addTest(NodeTests('test_set_volume_group'))
        suite.addTest(NodeTests('test_set_invalid_volume_group'))
        return suite

    def setUp(self):
        """Creates various objects and deletes any test VMs"""
        # Create MCVirt parser object
        self.parser = Parser(print_status=False)

        # Get an MCVirt instance
        self.mcvirt = MCVirt()

        self.original_ip_address = MCVirtConfig().get_config()['cluster']['cluster_ip']
        self.original_volume_group = MCVirtConfig().get_config()['vm_storage_vg']

    def tearDown(self):
        """Resets any values changed to the MCVirt config"""
        Node.set_cluster_ip_address(self.mcvirt, self.original_ip_address)
        Node.set_storage_volume_group(self.mcvirt, self.original_volume_group)
        self.mcvirt = None

    def test_set_ip_address(self):
        """Changes the cluster IP address using the argument parser"""
        test_ip_address = '1.1.1.1'
        self.parser.parse_arguments('node --set-ip-address %s' %
                                    test_ip_address,
                                    mcvirt_instance=self.mcvirt)
        self.assertEqual(MCVirtConfig().get_config()['cluster']['cluster_ip'], test_ip_address)

    def test_set_invalid_ip_address(self):
        test_fake_ip_addresses = [
            '1.1.1.256', 'test_string', '1.1.1', '1.2.3.4a'
        ]
        for ip_address in test_fake_ip_addresses:
            with self.assertRaises(InvalidIPAddressException):
                self.parser.parse_arguments('node --set-ip-address %s' %
                                            ip_address,
                                            mcvirt_instance=self.mcvirt)

    def test_set_volume_group(self):
        """Changes the cluster IP address using the argument parser"""
        test_vg = 'test-vg_name'
        self.parser.parse_arguments('node --set-vm-vg %s' % test_vg,
                                    mcvirt_instance=self.mcvirt)
        self.assertEqual(MCVirtConfig().get_config()['vm_storage_vg'], test_vg)

    def test_set_invalid_volume_group(self):
        test_fake_volume_groups = ('[adg', 'vg;', '@vg_name')
        for volume_group in test_fake_volume_groups:
            with self.assertRaises(InvalidVolumeGroupNameException):
                self.parser.parse_arguments('node --set-vm-vg %s' % volume_group,
                                            mcvirt_instance=self.mcvirt)

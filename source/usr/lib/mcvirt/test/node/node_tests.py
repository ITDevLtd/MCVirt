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

from mcvirt.exceptions import InvalidIPAddressException, InvalidVolumeGroupNameException
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.test.test_base import TestBase


class NodeTests(TestBase):
    """Provide unit tests for the functionality
    provided by the node subparser
    """

    @staticmethod
    def suite():
        """Return a test suite"""
        suite = unittest.TestSuite()
        suite.addTest(NodeTests('test_set_ip_address'))
        suite.addTest(NodeTests('test_set_invalid_ip_address'))
        suite.addTest(NodeTests('test_set_volume_group'))
        suite.addTest(NodeTests('test_set_invalid_volume_group'))
        return suite

    def setUp(self):
        """Create various objects and deletes any test VMs"""
        super(NodeTests, self).setUp()
        self.original_ip_address = MCVirtConfig().get_config()['cluster']['cluster_ip']
        self.original_volume_group = MCVirtConfig().get_config()['vm_storage_vg']

    def tearDown(self):
        """Reset any values changed to the MCVirt config"""
        def reset_config(config):
            config['cluster']['cluster_ip'] = self.original_ip_address
            config['vm_storage_vg'] = self.original_volume_group
        MCVirtConfig().update_config(reset_config, 'Reset node configurations')

        super(NodeTests, self).tearDown()

    def test_set_ip_address(self):
        """Change the cluster IP address using the argument parser"""
        test_ip_address = '1.1.1.1'
        self.parser.parse_arguments('node --set-ip-address %s' %
                                    test_ip_address)
        self.assertEqual(MCVirtConfig().get_config()['cluster']['cluster_ip'], test_ip_address)

    def test_set_invalid_ip_address(self):
        """Test the validity checks for IP addresses"""
        test_fake_ip_addresses = [
            '1.1.1.256', 'test_string', '1.1.1', '1.2.3.4a'
        ]
        for ip_address in test_fake_ip_addresses:
            with self.assertRaises(InvalidIPAddressException):
                self.parser.parse_arguments('node --set-ip-address %s' %
                                            ip_address)

    def test_set_volume_group(self):
        """Change the cluster IP address using the argument parser"""
        test_vg = 'test-vg_name'
        self.parser.parse_arguments('node --set-vm-vg %s' % test_vg)
        self.assertEqual(MCVirtConfig().get_config()['vm_storage_vg'], test_vg)

    def test_set_invalid_volume_group(self):
        """Test the validity checks for volume group name"""
        test_fake_volume_groups = ('[adg', 'vg;', '@vg_name')
        for volume_group in test_fake_volume_groups:
            with self.assertRaises(InvalidVolumeGroupNameException):
                self.parser.parse_arguments('node --set-vm-vg %s' % volume_group)

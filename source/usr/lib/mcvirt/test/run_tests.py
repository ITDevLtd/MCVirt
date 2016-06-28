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

import sys
import unittest

sys.path.insert(0, '/usr/lib')

from mcvirt.test.node.network_tests import NetworkTests
# from mcvirt.test.node.node_tests import NodeTests
from mcvirt.test.virtual_machine.virtual_machine_tests import VirtualMachineTests
# from mcvirt.test.auth_tests import AuthTests
# from mcvirt.test.virtual_machine.hard_drive.drbd_tests import DrbdTests
from mcvirt.test.update_tests import UpdateTests
# from mcvirt.test.virtual_machine.online_migrate_tests import OnlineMigrateTests

if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=4)
    # auth_test_suite = AuthTests.suite()
    virtual_machine_test_suite = VirtualMachineTests.suite()
    network_test_suite = NetworkTests.suite()
    # drbd_test_suite = DrbdTests.suite()
    update_test_suite = UpdateTests.suite()
    # online_migrate_test_suite = OnlineMigrateTests.suite()
    # node_test_suite = NodeTests.suite()
    all_tests = unittest.TestSuite([virtual_machine_test_suite, update_test_suite, network_test_suite])
    #    [virtual_machine_test_suite, network_test_suite, auth_test_suite,
    #     drbd_test_suite, update_test_suite, node_test_suite,
    #     online_migrate_test_suite])
    sys.exit(not runner.run(all_tests).wasSuccessful())

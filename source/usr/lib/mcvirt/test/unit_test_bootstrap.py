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

import unittest
import threading

from mcvirt.client.rpc import Connection
from mcvirt.test.node.network_tests import NetworkTests
from mcvirt.test.node.node_tests import NodeTests
from mcvirt.test.virtual_machine.virtual_machine_tests import VirtualMachineTests
from mcvirt.test.validation_tests import ValidationTests
from mcvirt.test.auth_tests import AuthTests
from mcvirt.test.virtual_machine.hard_drive.drbd_tests import DrbdTests
from mcvirt.test.update_tests import UpdateTests
from mcvirt.test.virtual_machine.online_migrate_tests import OnlineMigrateTests
from mcvirt.rpc.rpc_daemon import RpcNSMixinDaemon


class UnitTestBootstrap(object):
    """Bootstrap daemon with unit tests"""

    def __init__(self):
        """Create dameon and test suite objects"""
        # Configure daemon
        self.daemon_run = True
        self.daemon = RpcNSMixinDaemon()
        self.daemon_thread = threading.Thread(
            target=self.daemon.start,
            kwargs={'loopCondition': self.daemon_loop_condition}
        )

        self.runner = unittest.TextTestRunner(verbosity=4)
        auth_test_suite = AuthTests.suite()
        virtual_machine_test_suite = VirtualMachineTests.suite()
        network_test_suite = NetworkTests.suite()
        drbd_test_suite = DrbdTests.suite()
        update_test_suite = UpdateTests.suite()
        node_test_suite = NodeTests.suite()
        online_migrate_test_suite = OnlineMigrateTests.suite()
        validation_test_suite = ValidationTests.suite()
        OnlineMigrateTests.RPC_DAEMON = self.daemon
        self.all_tests = unittest.TestSuite([
            virtual_machine_test_suite,
            network_test_suite,
            drbd_test_suite,
            update_test_suite,
            node_test_suite,
            online_migrate_test_suite,
            validation_test_suite,
            auth_test_suite
        ])

    def daemon_loop_condition(self):
        """Provide a condition for the daemon loop"""
        return self.daemon_run

    def start(self):
        """Start the daemon, run the unit tests and tear down"""
        try:
            # Attempt to start daemon
            self.daemon_thread.start()

            # Attempt to run tests
            success = self.runner.run(self.all_tests).wasSuccessful()
        finally:
            # Set the run condition flag for daemon to False in order to
            # stop on next loop
            self.daemon_run = False
            OnlineMigrateTests.RPC_DAEMON = None
            try:
                # Perform final connection to daemon to ensure that it loops
                # to stop.
                Connection(username='fake', password='fake')
            except:
                pass

            # Wait for daemon to stop
            self.daemon_thread.join()

        # Return success state of tests
        return success

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
import threading

from mcvirt.rpc.lock import locking_method
from mcvirt.test.test_base import TestBase


class LockTests(TestBase):
    """Provide unit tests for the functionality
    provided by the node subparser
    """

    @staticmethod
    def suite():
        """Return a test suite"""
        suite = unittest.TestSuite()
        suite.addTest(LockTests('test_method_lock_rpc'))
        suite.addTest(LockTests('test_method_lock_escape_return'))
        return suite

    def test_method_lock_rpc(self):
        """Test whether locks can be cleared over the RPC"""

        thread_is_running_event = threading.Event()
        thread_should_stop_event = threading.Event()

        @locking_method()
        def hold_lock_forever(self):
            while not thread_should_stop_event.is_set():
                thread_is_running_event.set()

        @locking_method()
        def take_lock(self):
            return True

        # Test nothing else running
        testing_thread = threading.Thread(target=take_lock, args=(self,))
        testing_thread.start()
        testing_thread.join(2)

        # Try to take a lock which has already been taken
        locking_thread = threading.Thread(target=hold_lock_forever, args=(self,))
        locking_thread.start()

        # wait for the locking thread to take its lock
        thread_is_running_event.wait()

        testing_thread = threading.Thread(target=take_lock, args=(self,))
        testing_thread.start()

        # This should fail:
        testing_thread.join(2)

        # check that the thread is still running after 2 seconds, because it'll still be locked.
        self.assertTrue(testing_thread.is_alive())

        # Fix the problem by clearing the lock
        self.parser.parse_arguments("clear-method-lock")

        # This should succeed:
        testing_thread.join(2)

        # check that the thread has stopped
        self.assertFalse(testing_thread.is_alive())

        # Clean up
        thread_should_stop_event.set()
        locking_thread.join()

    def test_method_lock_escape_return(self):
            """Test whether locks can be cleared and clear_method_lock returns accurateley"""

            thread_is_running_event = threading.Event()
            thread_should_stop_event = threading.Event()

            @locking_method()
            def hold_lock_forever(self):
                while not thread_should_stop_event.is_set():
                    thread_is_running_event.set()

            node = self.rpc.get_connection('node')
            self.assertFalse(node.clear_method_lock())

            # Try to take a lock which has already been taken
            locking_thread = threading.Thread(target=hold_lock_forever, args=(self,))
            locking_thread.start()

            # wait for the locking thread to take its lock
            thread_is_running_event.wait()

            self.assertTrue(node.clear_method_lock())
            self.assertFalse(node.clear_method_lock())

            # Clean up
            thread_should_stop_event.set()
            locking_thread.join()

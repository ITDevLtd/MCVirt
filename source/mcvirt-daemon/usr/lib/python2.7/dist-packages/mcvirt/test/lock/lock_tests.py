# pylint: disable=C0103
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
from time import sleep
import threading

from mcvirt.test.test_base import TestBase
from mcvirt.rpc.expose_method import Expose
from mcvirt.exceptions import TaskCancelledError
from mcvirt.rpc.pyro_object import PyroObject


class LockingFunctions(PyroObject):
    """Provide test methods for testing locking"""

    def __init__(self):
        """Create events"""
        self.thread_should_stop_event = threading.Event()
        self.thread_is_running_event = threading.Event()

    @Expose
    def tick(self):
        sleep(1.0/10)

    @Expose(locking=True)
    def hold_lock_forever(self):
        """Hold lock forever."""
        while not self.thread_should_stop_event.is_set():
            self.thread_is_running_event.set()
            try:
                self.tick()
            except TaskCancelledError:
                self.thread_should_stop_event.set()

    @Expose(locking=True)
    def take_lock(self):
        """Take lock."""
        return True

    def cleanup(self):
        """Clean up"""
        self.thread_should_stop_event.set()
        self.locking_thread.join()
        #self.thread_should_stop_event.reset()
        #self.thread_is_running_event.reset()


class LockTests(TestBase):
    """Provide unit tests for the functionality
    provided by the node subparser
    """

    @staticmethod
    def suite():
        """Return a test suite."""
        suite = unittest.TestSuite()
        suite.addTest(LockTests('test_method_lock_rpc'))
        suite.addTest(LockTests('test_method_lock_escape_return'))
        return suite

    def setUp(self):
        """Create network adapter factory."""
        super(LockTests, self).setUp()
        self.locking_functions_obj = LockingFunctions()
        LockTests.RPC_DAEMON.register(self.locking_functions_obj,
                                      objectId='test_locking_functions',
                                      force=True)
        self.locking_functions_conn = self.rpc.get_connection(
            'test_locking_functions')

    def tearDown(self):
        """Tear down network adapter factory."""
        # Reset locking functions object
        self.locking_functions_obj.cleanup()
        self.locking_functions_conn = None
        super(LockTests, self).tearDown()

    def test_method_lock_rpc(self):
        """Test whether locks can be cleared over the RPC."""

        def s_take_lock(self):
            """Start take_lock thread"""
            self.locking_functions_conn.take_lock()

        def s_hold_lock_forever(self):
            """Start hold lock forever thread"""
            self.locking_functions_conn.hold_lock_forever()

        # Test nothing else running
        testing_thread = threading.Thread(target=s_take_lock, args=(self,))
        # testing_thread.daemon = True
        testing_thread.start()
        testing_thread.join(2)

        # Try to take a lock which has already been taken
        locking_thread = threading.Thread(target=s_hold_lock_forever, args=(self,))
        locking_thread.daemon = True
        locking_thread.start()

        # wait for the locking thread to take its lock
        self.locking_functions_obj.thread_is_running_event.wait()

        testing_thread = threading.Thread(target=s_take_lock, args=(self,))
        testing_thread.daemon = True
        testing_thread.start()

        # This should return without the thread ending
        testing_thread.join(2)

        # check that the thread is still running after 2 seconds, because it'll still be locked.
        self.assertTrue(testing_thread.is_alive())

        # Fix the problem by clearing the lock
        self.parser.parse_arguments("clear-method-lock")

        # This should succeed:
        testing_thread.join(10)

        # check that the thread has stopped
        self.assertFalse(testing_thread.is_alive())
        print 'END OF TEST!!!'

    def test_method_lock_escape_return(self):
        """Test whether locks can be cleared and clear_method_lock returns accurateley."""

        def s_hold_lock_forever(self):
            """Start hold lock forever thread"""
            self.locking_functions_conn.hold_lock_forever()

        task_scheduler = self.rpc.get_connection('task_scheduler')
        self.assertFalse(task_scheduler.cancel_current_task())

        # Try to take a lock which has already been taken
        locking_thread = threading.Thread(target=s_hold_lock_forever, args=(self,))
        locking_thread.start()

        # wait for the locking thread to take its lock
        self.locking_functions_obj.thread_is_running_event.wait()

        self.assertTrue(task_scheduler.cancel_current_task())
        self.assertFalse(task_scheduler.cancel_current_task())

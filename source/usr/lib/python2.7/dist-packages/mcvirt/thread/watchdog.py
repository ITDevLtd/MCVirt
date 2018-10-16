# Copyright (c) 2018 - I.T. Dev Ltd
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

from enum import Enum
import Pyro4

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.syslogger import Syslogger
from mcvirt.utils import get_hostname
from mcvirt.exceptions import TimeoutExceededSerialLockError


WATCHDOG_STATES = Enum('WATCHDOG_STATES',
                       ['INITIALISING',  # Daemon started after VM, awaiting
                                         # first communications
                        'STARTUP',  # VM starting being reset
                        'ACTIVE',  # VM responded to last ping
                        'WAITING_RESP',  # Sent ping, awaiting response
                        'FAILING',  # VM falied to respond to last ping,
                                    # currently in retry period
                        'FAILED'])  # VM has failed to respond to pings and to be reset


class WatchdogManager(PyroObject):
    """Object to configure and create watchdog daemons"""

    def __init__(self):
        """Intialise state of watchdogs"""
        self.watchdogs = {}

    def initialise(self):
        """Detect running VMs on local node and create watchdog daemon"""
        # Check all VMs
        for vm in self._get_registered_object(
                'virtual_machine_factory').getAllVirtualMachines(node=get_hostname()):
            # If VM is registered locally, is running and watchdog is
            # enabled, create watchdog and register
            if (vm.isRegisteredLocally() and
                    vm.is_running and
                    vm.is_watchdog_enabled()):
                Syslogger.logger().debug('Registering watchdog for: %s' % vm.get_name())
                self.register_virtual_machine(vm)

    def register_virtual_machine(self, virtual_machine):
        """Create watchdog and register"""
        wd = Watchdog(virtual_machine)
        wd.initialise()
        self.watchdogs[virtual_machine.get_name()] = wd

    def cancel(self):
        """Stop all threads"""
        for wd in self.watchdogs.values():
            wd.repeat = False
            wd.timer.cancel()


class Watchdog(RepeatTimer):

    def __init__(self, virtual_machine, *args, **kwargs):
        """Store virtual machine and initialise state"""
        self.virtual_machine = virtual_machine
        self.state = WATCHDOG_STATES.INITIALISING
        self.fail_count = 0
        super(Watchdog, self).__init__(*args, **kwargs)

    def set_state(self, new_state):
        """Set state"""
        Syslogger.logger().debug(
            'State for (%s) changed from %s to %s' %
            (self.virtual_machine.get_name(),
             self.state, new_state))
        self.state = new_state

    @property
    def interval(self):
        """Return the timer interval"""
        return self.virtual_machine.get_watchdog_interval()

    def run(self):
        """Perform watchdog check"""
        Syslogger.logger().debug('Watchdog checking: %s' %
                                 self.virtual_machine.get_name())
        Pyro4.current_context.INTERNAL_REQUEST = True

        if self.state in [WATCHDOG_STATES.ACTIVE, WATCHDOG_STATES.FAILING]:
            self.set_state(WATCHDOG_STATES.WAITING_RESP)

        agent_conn = self.virtual_machine.get_agent_connection()

        resp = None
        def ping_agent(conn):
            """Send request to agent and ensure it responds"""
            conn.send('ping\n')
            resp = conn.readline().strip()

        try:
            agent_conn.wait_lock(ping_agent)
        except TimeoutExceededSerialLockError:
            pass

        # If response is valid, reset counter and state
        if resp == 'pong':
            self.fail_count = 0
            self.set_state(WATCHDOG_STATES.ACTIVE)
        else:
            self.fail_count += 1
            self.set_state(WATCHDOG_STATES.FAILING)

            if self.fail_count >= self.virtual_machine.get_watchdog_reset_fail_count():
                self.set_state(WATCHDOG_STATES.FAILED)
                Syslogger.logger().error(
                    'Watchdog for VM failed. Starting reset: %s' %
                    self.virtual_machine.get_name())

                # Reset VM
                self.virtual_machine.reset()

                # Reset states
                self.set_state(WATCHDOG_STATES.STARTUP)


        Pyro4.current_context.INTERNAL_REQUEST = False
        Syslogger.logger().debug('Watchdog complete: %s' %
                                 self.virtual_machine.get_name())
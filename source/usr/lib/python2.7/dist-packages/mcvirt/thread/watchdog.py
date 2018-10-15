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

import Pyro4
from enum import Enum

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.constants import AutoStartStates
from mcvirt.rpc.expose_method import Expose
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject


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
        for vm in self._get_registered_object('virtual_machine_factory').getAllVirtualMachines():

            # If VM is registered locally and is running, create watchdog and register
            if vm.isRegisteredLocally() and vm.is_running():
                self.register_virtual_machine(vm)

    def register_virtual_machine(self, virtual_machine):
        """Create watchdog and register"""
        wd = Watchdog(virtual_machine)
        wd.initialise()
        self.watchdogs[virtual_machine.get_name()] = wd


class Watchdog(RepeatTimer):

    def __init__(self, virtual_machine, *args, **kwargs):
        """Store virtual machine and initialise state"""
        self.virtual_machine = virtual_machine
        self.state = WATCHDOG_STATES.INITIALISING
        super(Watchdog, self).__init__(*args, **kwargs)

    @property
    def interval(self):
        """Return the timer interval"""
        return self.virtual_machine.get_watchdog_interval()

    @Expose()
    def get_autostart_interval(self):
        """Return the autostart interval for the node"""
        return self._get_registered_object('mcvirt_config')().get_config()['autostart_interval']

    @Expose(locking=True)
    def set_autostart_interval(self, interval_time):
        """Update the autostart interval for the node"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_NODE)
        ArgumentValidator.validate_integer(interval_time)
        interval_time = int(interval_time)

        def update_config(config):
            config['autostart_interval'] = interval_time
        self._get_registered_object('mcvirt_config')().update_config(update_config,
                                                                     'Update autostart interval')

        if self._is_cluster_master:

            def remote_update(node):
                autostart_watchdog = node.get_connection('autostart_watchdog')
                autostart_watchdog.set_autostart_interval(interval_time)
            cluster = self._get_registered_object('cluster')
            cluster.run_remote_command(remote_update)

        # If the timer has been set to 0, disable the timer
        if interval_time == 0:
            self.repeat = False
            self.timer.cancel()
            self.timer = None
        else:
            # Otherwise update the running timer
            if self.timer is None:
                self.repeat = True
                self.repeat_run()

    def run(self):
        """Perform ON_POLL autostart"""
        Pyro4.current_context.INTERNAL_REQUEST = True
        vm_factory = self._get_registered_object('virtual_machine_factory')
        vm_factory.autostart(AutoStartStates.ON_POLL)
        Pyro4.current_context.INTERNAL_REQUEST = False

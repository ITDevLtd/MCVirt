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
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import dict_merge
from mcvirt.auth.permissions import PERMISSIONS


WATCHDOG_STATES = Enum(
    'WATCHDOG_STATES',
    [
        'INITIALISING',  # Daemon started after VM, awaiting
                         # first communications
        'STARTUP',  # VM starting being reset
        'ACTIVE',  # VM responded to last ping
        'WAITING_RESP',  # Sent ping, awaiting response
        'FAILING',  # VM falied to respond to last ping,
                    # currently in retry period
        'FAILED',  # VM has failed to respond to pings and to be reset
        'NOT_SUITABLE'  # VM either not registered locally, running
                        # or watchdog not enabled to run
    ]
)


class WatchdogFactory(PyroObject):
    """Object to configure and create watchdog daemons."""

    def __init__(self):
        """Intialise state of watchdogs."""
        self.watchdogs = {}

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the watchdog factory on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('watchdog_factory')

    def initialise(self):
        """Detect running VMs on local node and create watchdog daemon."""
        # Check all VMs
        for virtual_machine in self.po__get_registered_object(
                'virtual_machine_factory').get_all_virtual_machines():

            Syslogger.logger().debug('Registering watchdog for: %s' % virtual_machine.get_name())
            self.start_watchdog(virtual_machine)

    def start_watchdog(self, virtual_machine):
        """Create watchdog and start."""
        watchdog = self.get_watchdog(virtual_machine)
        watchdog.initialise()

    def stop_watchdog(self, virtual_machine):
        """Stop watchdog."""
        watchdog = self.get_watchdog(virtual_machine)
        watchdog.cancel()

    def get_watchdog(self, virtual_machine):
        """Get a watchdog obect for a given virtual machine."""
        if virtual_machine.get_name() not in self.watchdogs:
            self.watchdogs[virtual_machine.get_name()] = Watchdog(virtual_machine)
        return self.watchdogs[virtual_machine.get_name()]

    def cancel(self):
        """Stop all threads."""
        for watchdog in list(self.watchdogs.values()):
            watchdog.repeat = False
            watchdog.cancel()

    @Expose(locking=True, remote_nodes=True, support_callback=True)
    def update_watchdog_config(self, change_dict, reason, _f):
        """Update global watchdog config using dict."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def update_config(config):
            """Update mcvirt config."""
            _f.add_undo_argument(original_config=dict(config['watchdog']))
            dict_merge(config['watchdog'], change_dict)

        MCVirtConfig().update_config(update_config, reason)

    @Expose(locking=True)
    def undo__update_vm_config(self, change_dict, reason, _f, original_config=None):
        """Undo config change."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser',
                                                             allow_indirect=True)

        def revert_config(config):
            """Revert config."""
            config['watchdog'] = original_config

        if original_config is not None:
            MCVirtConfig().update_config('Revert: %s' % reason, revert_config)

    @Expose(locking=True)
    def set_global_interval(self, interval):
        """Set global default watchdog check interval."""
        ArgumentValidator.validate_positive_integer(interval)

        # Check permissions
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_GLOBAL_WATCHDOG)

        self.update_watchdog_config(
            change_dict={'interval': interval},
            reason='Update global watchdog interval',
            nodes=self.po__get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def set_global_reset_fail_count(self, count):
        """Set global default watchdog reset fail count."""
        ArgumentValidator.validate_positive_integer(count)

        # Check permissions
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_GLOBAL_WATCHDOG)

        self.update_watchdog_config(
            change_dict={'reset_fail_count': count},
            reason='Update global watchdog reset fail count',
            nodes=self.po__get_registered_object('cluster').get_nodes(include_local=True))

    @Expose(locking=True)
    def set_global_boot_wait(self, wait):
        """Set the global default boot wait period."""
        ArgumentValidator.validate_positive_integer(wait)

        # Check permissions
        self.po__get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_GLOBAL_WATCHDOG)

        self.update_watchdog_config(
            change_dict={'boot_wait': wait},
            reason='Update global watchdog boot wait period',
            nodes=self.po__get_registered_object('cluster').get_nodes(include_local=True))


class Watchdog(RepeatTimer):
    """Watchdog timer thread for checking VM status."""

    def __init__(self, virtual_machine, *args, **kwargs):
        """Store virtual machine and initialise state."""
        self.virtual_machine = virtual_machine
        self.state = WATCHDOG_STATES.INITIALISING
        self.fail_count = 0
        super(Watchdog, self).__init__(*args, **kwargs)

    def set_state(self, new_state):
        """Set state."""
        if self.state != new_state:
            Syslogger.logger().debug(
                'State for (%s) changed from %s to %s' %
                (self.virtual_machine.get_name(),
                 self.state, new_state))
            self.state = new_state

    @property
    def interval(self):
        """Return the timer interval."""
        if self.state is WATCHDOG_STATES.STARTUP:
            boot_wait = self.virtual_machine.get_watchdog_boot_wait()
            Syslogger.logger().debug(
                'In boot period, interval is: %s' % boot_wait)
            return boot_wait
        else:
            return self.virtual_machine.get_watchdog_interval()

    def run(self):
        """Perform watchdog check."""
        Syslogger.logger().debug('Watchdog checking: %s' %
                                 self.virtual_machine.get_name())
        Pyro4.current_context.INTERNAL_REQUEST = True

        # Ensure that VM is registered locally, running and watchog is enabled
        if not (self.virtual_machine.is_watchdog_enabled() and
                self.virtual_machine.isRegisteredLocally() and
                self.virtual_machine.is_running):
            self.set_state(WATCHDOG_STATES.NOT_SUITABLE)
            Syslogger.logger().info(
                'Watchdog not run: %s' %
                self.virtual_machine.get_name())
            return

        if self.state in [WATCHDOG_STATES.ACTIVE, WATCHDOG_STATES.FAILING]:
            self.set_state(WATCHDOG_STATES.WAITING_RESP)

        agent_conn = self.virtual_machine.get_agent_connection()

        resp = None
        try:
            resp = agent_conn.wait_lock(command='ping')
        except Exception as e:
            Syslogger.logger().error(e)

        # If response is valid, reset counter and state
        if resp == 'pong':
            self.fail_count = 0
            self.set_state(WATCHDOG_STATES.ACTIVE)
        else:
            self.fail_count += 1
            self.set_state(WATCHDOG_STATES.FAILING)

            if self.fail_count >= self.virtual_machine.get_watchdog_reset_fail_count():
                # Reset fail count
                self.fail_count = 0

                self.set_state(WATCHDOG_STATES.FAILED)
                Syslogger.logger().error(
                    'Watchdog for VM failed. Starting reset: %s' %
                    self.virtual_machine.get_name())

                # Reset VM
                self.virtual_machine.reset()

                # Reset WATCHDOG_STATES
                self.set_state(WATCHDOG_STATES.STARTUP)

        Pyro4.current_context.INTERNAL_REQUEST = False
        Syslogger.logger().debug('Watchdog complete: %s' %
                                 self.virtual_machine.get_name())

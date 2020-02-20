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

import Pyro4

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.constants import AutoStartStates
from mcvirt.rpc.expose_method import Expose
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.syslogger import Syslogger


class AutoStartWatchdog(RepeatTimer):
    """Object to perform regular checks to determine that VMs are running."""

    @property
    def interval(self):
        """Return the timer interval."""
        return self.get_autostart_interval()

    @Expose()
    def get_autostart_interval(self):
        """Return the autostart interval for the node."""
        return self.po__get_registered_object('mcvirt_config')().get_config()['autostart_interval']

    @Expose(locking=True)
    def set_autostart_interval(self, interval_time):
        """Update the autostart interval for the node."""
        self.po__get_registered_object('auth').assert_permission(PERMISSIONS.MANAGE_NODE)
        ArgumentValidator.validate_integer(interval_time)
        interval_time = int(interval_time)

        def update_config(config):
            """Update autostart interval in MCVirt config."""
            config['autostart_interval'] = interval_time
        self.po__get_registered_object('mcvirt_config')().update_config(update_config,
                                                                     'Update autostart interval')

        if self.po__is_cluster_master:

            def remote_update(node):
                """Update autostart interval on remote node."""
                autostart_watchdog = node.get_connection('autostart_watchdog')
                autostart_watchdog.set_autostart_interval(interval_time)
            cluster = self.po__get_registered_object('cluster')
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

    def initialise(self):
        """Perform the ON_BOOT autostart and start timer."""
        Pyro4.current_context.INTERNAL_REQUEST = True
        vm_factory = self.po__get_registered_object('virtual_machine_factory')
        try:
            vm_factory.autostart(AutoStartStates.ON_BOOT)
        except Exception as exc:
            Syslogger.logger().error('Error during autostart ON_BOOT: %s' % str(exc))
        Pyro4.current_context.INTERNAL_REQUEST = False
        super(AutoStartWatchdog, self).initialise()

    def run(self):
        """Perform ON_POLL autostart."""
        Pyro4.current_context.INTERNAL_REQUEST = True
        vm_factory = self.po__get_registered_object('virtual_machine_factory')
        try:
            vm_factory.autostart(AutoStartStates.ON_POLL)
        except Exception as exc:
            Syslogger.logger().error('Error during autostart ON_POLL : %s' % str(exc))
        Pyro4.current_context.INTERNAL_REQUEST = False

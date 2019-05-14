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

import json
from datetime import datetime
import Pyro4

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.syslogger import Syslogger
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import dict_merge
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.constants import (StatisticsDeviceType,
                              StatisticsStatType)


class VirtualMachineStatisticsFactory(PyroObject):
    """Object to configure and create statistics daemons."""

    def __init__(self):
        """Intialise state of statisticss."""
        self.statistics_agents = {}

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the statistics factory on a remote node."""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('virtual_machine_statistics_factory')

    def initialise(self):
        """Detect running VMs on local node and create statistics agents."""
        # Check all VMs
        for virtual_machine in self._get_registered_object(
                'virtual_machine_factory').get_all_virtual_machines():

            Syslogger.logger().debug('Registering statistics daemon for: %s' %
                                     virtual_machine.get_name())
            self.start_statistics(virtual_machine)

    def start_statistics(self, virtual_machine):
        """Create statistics agents and start."""
        stats = self.get_statistics_agent(virtual_machine)
        stats.initialise()

    def stop_statistics(self, virtual_machine):
        """Stop statistics."""
        stats = self.get_statistics_agent(virtual_machine)
        stats.cancel()

    def get_statistics_agent(self, virtual_machine):
        """Get a statistics obect for a given virtual machine."""
        if virtual_machine.get_name() not in self.statistics_agents:
            stats_agent = VirtualMachineStatisticsAgent(virtual_machine)
            self._register_object(stats_agent)
            self.statistics_agents[virtual_machine.get_name()] = stats_agent
        return self.statistics_agents[virtual_machine.get_name()]

    def cancel(self):
        """Stop all threads."""
        for stats_agent in self.statistics_agents.values():
            stats_agent.repeat = False
            stats_agent.cancel()

    @Expose(locking=True)
    def set_global_interval(self, interval):
        """Set global default statistics check interval."""
        ArgumentValidator.validate_positive_integer(interval)

        # Check permissions
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MANAGE_GLOBAL_WATCHDOG)

        self.update_statistics_config(
            change_dict={'interval': interval},
            reason='Update global statistics interval',
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))


class VirtualMachineStatisticsAgent(RepeatTimer):
    """Statistics agent timer thread for checking VM stats."""

    def __init__(self, virtual_machine, *args, **kwargs):
        """Store virtual machine."""
        self.virtual_machine = virtual_machine
        super(VirtualMachineStatisticsAgent, self).__init__(*args, **kwargs)

    @property
    def interval(self):
        """Return the timer interval."""
        # @TODO This will be slow
        return MCVirtConfig().get_config()['statistics']['interval']

    def insert_into_stat_db(self):
        """Add statistics to statistics database."""
        db_factory = self._get_registered_object('database_factory')
        db_rows = [
            (StatisticsDeviceType.VIRTUAL_MACHINE.value,
             self.virtual_machine.id_,
             StatisticsStatType.CPU_USAGE.value,
             self.virtual_machine.current_guest_cpu_usage,
             "{:%s}".format(datetime.now())),

            (StatisticsDeviceType.VIRTUAL_MACHINE.value,
             self.virtual_machine.id_,
             StatisticsStatType.MEMORY_USAGE.value,
             self.virtual_machine.current_guest_memory_usage,
             "{:%s}".format(datetime.now()))
        ]
        with db_factory.get_locking_connection() as db_inst:
            db_inst.cursor.executemany(
                """INSERT INTO stats(
                    device_type, device_id, stat_type, stat_value, stat_date
                ) VALUES(?, ?, ?, ?, ?)""",
                db_rows)

    def run(self):
        """Perform statistics check."""
        Syslogger.logger().debug('Statistics daemon checking: %s' %
                                 self.virtual_machine.get_name())
        Pyro4.current_context.INTERNAL_REQUEST = True

        # Ensure that VM is registered locally, running and watchog is enabled
        if not (self.virtual_machine.isRegisteredLocally() and
                self.virtual_machine.is_running):
            Syslogger.logger().info(
                'Statistics daemon not run: %s' %
                self.virtual_machine.get_name())
            return

        agent_conn = self.virtual_machine.get_agent_connection()

        resp = None
        try:
            resp = agent_conn.wait_lock(command='stats')
        except Exception, e:
            Syslogger.logger().error(e)

        if resp is not None:
            resp = json.loads(resp)

            self.virtual_machine.current_guest_memory_usage = (
                resp['memory_usage']
                if 'memory_usage' in resp else
                None)
            self.virtual_machine.current_guest_cpu_usage = (
                resp['cpu_usage']
                if 'cpu_usage' in resp else
                None)

        self.insert_into_stat_db()

        Pyro4.current_context.INTERNAL_REQUEST = False
        Syslogger.logger().debug('Statistics daemon complete: %s' %
                                 self.virtual_machine.get_name())

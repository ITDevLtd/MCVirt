# Copyright (c) 2018 - Matt Comben
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

from datetime import datetime
import Pyro4

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.constants import (AutoStartStates,
                              StatisticsDeviceType,
                              StatisticsStatType)
from mcvirt.rpc.expose_method import Expose
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.os_stats import OSStats
from mcvirt.syslogger import Syslogger
from mcvirt.utils import get_hostname


class HostStatistics(RepeatTimer):
    """Object to perform regular cpu and memory stats gathering on host"""

    def __init__(self, *args, **kwargs):
        self._cpu_usage = 0
        self._memory_usage = 0
        super(HostStatistics, self).__init__(*args, **kwargs)

    @Expose()
    def get_cpu_usage_string(self):
        """Return CPU usage in %"""
        return '%s%%' % self._cpu_usage

    @Expose()
    def get_memory_usage_string(self):
        """Return memory usage in %"""
        return '%s%%' % self._memory_usage

    @property
    def interval(self):
        """Return the timer interval"""
        return self.get_autostart_interval()

    @Expose()
    def get_autostart_interval(self):
        """Return the statistics interval for the node"""
        return self._get_registered_object(
            'mcvirt_config')().get_config()['statistics']['interval']

    def insert_into_stat_db(self):
        """Add statistics to statistics database"""
        db_factory = self._get_registered_object('database_factory')
        db_rows = [
            (StatisticsDeviceType.HOST.value, get_hostname(),
             StatisticsStatType.CPU_USAGE.value, self._cpu_usage,
             "{:%s}".format(datetime.now())),

            (StatisticsDeviceType.HOST.value, get_hostname(),
             StatisticsStatType.MEMORY_USAGE.value, self._memory_usage,
             "{:%s}".format(datetime.now()))
        ]
        with db_factory.get_locking_connection() as db_inst:
            db_inst.cursor.executemany(
                """INSERT INTO stats(
                    device_type, device_id, stat_type, stat_value, stat_date
                ) VALUES(?, ?, ?, ?, ?)""",
                db_rows)

    def run(self):
        """Obtain CPU and memory statistics"""
        Pyro4.current_context.INTERNAL_REQUEST = True
        Syslogger.logger().debug('Starting host stats gathering')
        self._cpu_usage = OSStats.get_cpu_usage()
        self._memory_usage = OSStats.get_ram_usage()
        self.insert_into_stat_db()
        Syslogger.logger().debug('Completed host stats gathering')

        Pyro4.current_context.INTERNAL_REQUEST = False

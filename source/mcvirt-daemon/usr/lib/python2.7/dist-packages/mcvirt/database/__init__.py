"""Module for distributed database across the cluster."""

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

from threading import Lock, Timer
import gc
from datetime import datetime, timedelta
import sqlite3

import Pyro4

from mcvirt.rpc.expose_method import Expose
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.exceptions import (DatabaseClassAlreadyInstanciatedError,
                               DoNotHaveDatabaseConnectionLockError,
                               UnableToObtainDatabaseLockError)
from mcvirt.constants import DirectoryLocation, StatisticsDeviceType
from . import schema_migrations as migrations
from mcvirt.syslogger import Syslogger
from mcvirt.thread.repeat_timer import RepeatTimer


class DatabaseFactory(PyroObject):
    """Provide functionality to obtain locked database connection,
    database syncronisation and creation
    """

    # A lock for the class itself, so the class
    # can only be instanciated once
    SINGLETON_LOCK = Lock()

    # A connection lock, ensuring that database update
    # callback query can be performed at once
    CONNECTION_LOCK = Lock()

    def __init__(self):
        """Obtain singleton lock and create connection to DB."""
        if not DatabaseFactory.SINGLETON_LOCK.acquire(False):
            raise DatabaseClassAlreadyInstanciatedError(
                'Database class has already been instanciated')

    def initialise(self):
        """Perform DB migration."""
        with self.get_locking_connection() as db_inst:
            self._schema_migration(db_inst)

    def __del__(self):
        """On object delection, wait for connection to clear
        and remove sqlite object and singleton lock
        """
        gc.collect()
        DatabaseFactory.SINGLETON_LOCK.release()

    def get_locking_connection(self, perform_sync=True):
        """Obtain instance of database connection."""
        db_object = DatabaseConnection(self, perform_sync=perform_sync)
        self.po__register_object(db_object)
        return db_object

    def get_sqlite_object(self):
        """Retrun the SQLite database object."""
        return sqlite3.connect(DirectoryLocation.SQLITE_DATABASE)

    @staticmethod
    def obtain_db_conn_lock():
        """Obtain database connection lock."""
        return DatabaseFactory.CONNECTION_LOCK.acquire()

    @staticmethod
    def release_db_conn_lock():
        """Release datbase connection lock."""
        DatabaseFactory.CONNECTION_LOCK.release()

    def _get_schema_version(self, db_inst):
        """Get database schema version."""
        res = db_inst.cursor.execute(
            """SELECT name FROM sqlite_master WHERE type='table' AND name='mcvirt_schema';""")

        # If there is no table for schema
        if res.fetchone() is None:
            return 0

        # Otherwise obtain the schema version from the file
        res = db_inst.cursor.execute(
            """SELECT version FROM mcvirt_schema;""")
        version = res.fetchone()
        return version if version is not None else 0

    def _schema_migration(self, db_inst):
        """Perform schema miagrations."""
        Syslogger.logger().info('Performing DB migration')
        schema_version = self._get_schema_version(db_inst)
        Syslogger.logger().info('Current DB schema version: %s' % schema_version)

        if schema_version < 1:
            migrations.v1.migrate(db_inst)

        if schema_version < migrations.SCHEMA_VERSION:
            migrations.update_schema_version(db_inst)

    @Expose()
    def get_latest_stat(self, device_type, device_id):
        """Obtain latest statistics date."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser')
        local_latest = None
        with self.get_locking_connection(perform_sync=False) as db_inst:
            res = db_inst.cursor.execute(
                """SELECT max(stat_date) FROM stats WHERE device_type=? AND device_id=?""",
                (device_type, device_id))
            local_latest = res.fetchone()
            if local_latest:
                local_latest = local_latest[0]
        return local_latest if local_latest else 0

    def get_statistics(self, device_type, device_id, from_date):
        """Obtain ist of statistics from a given date."""
        data_set = []
        with self.get_locking_connection(perform_sync=False) as db_inst:
            res = db_inst.cursor.execute(
                """SELECT stat_date, stat_value, stat_type FROM stats
                   WHERE device_type=? AND device_id=? AND stat_date > ?""",
                (device_type, device_id, from_date))
            for stat in res:
                data_set.append(list(stat))
        return data_set

    @Expose()
    def import_statistics(self, device_type, device_id, stats):
        """Import stats into local db."""
        self.po__get_registered_object('auth').assert_user_type('ClusterUser')
        for stat in stats:
            stat.append(device_type)
            stat.append(device_id)
        with self.get_locking_connection(perform_sync=False) as db_inst:
            db_inst.cursor.executemany(
                """INSERT INTO stats(stat_date, stat_value, stat_type, device_type, device_id)
                   VALUES(?, ?, ?, ?, ?)""",
                stats)

    def sync(self):
        """Syncronise all local data with remote nodes."""
        # @TODO This is just waiting for a dead lock
        # Need to implement global cluster lock

        virtual_machines = self.po__get_registered_object(
            'virtual_machine_factory').get_all_virtual_machines()
        cluster = self.po__get_registered_object('cluster')
        for node in cluster.get_nodes():
            node_object = cluster.get_remote_node(node)
            remote_db_fact = node_object.get_connection('database_factory')

            for device_id, device_type in (
                    [(vm.id_, StatisticsDeviceType.VIRTUAL_MACHINE.value)
                     for vm in virtual_machines] +
                    [(node, StatisticsDeviceType.HOST.value)
                     for node in cluster.get_nodes(return_all=True,
                                                   include_local=True)]):

                local_latest = self.get_latest_stat(device_type, device_id)

                remote_latest = remote_db_fact.get_latest_stat(device_type,
                                                               device_id)

                # If local data is newer than remote data,
                # push the changes
                if local_latest > remote_latest:
                    Syslogger.logger().info(
                        'Syncing stats from %s to %s for %s %s:%s' %
                        (remote_latest, local_latest, node, device_type, device_id))
                    push_data = self.get_statistics(device_type=device_type,
                                                    device_id=device_id,
                                                    from_date=remote_latest)
                    remote_db_fact.import_statistics(device_type=device_type,
                                                     device_id=device_id,
                                                     stats=push_data)
                    Syslogger.logger().info('Complete single stat sync')


class DatabaseConnection(PyroObject):
    """Provide a locking connecftion to the sqlite database object."""

    def __init__(self, database, perform_sync):
        """Obtain the database connection."""
        self.has_lock = False
        self._database = database
        self._perform_sync = perform_sync
        self._sqlite_object = self._database.get_sqlite_object()

    def __enter__(self):
        """Obtain connection lock."""
        if not self._database.obtain_db_conn_lock():
            raise UnableToObtainDatabaseLockError('Unable to obtain database lock')
        self.has_lock = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Release lock."""
        # If an exception was raised, rollback the DB changes
        if exc_type is not None:
            Syslogger.logger().error('Error during db lock: %s' % traceback)
            self.get_db_object().rollback()

        # Otherwise, commit changes
        else:
            self.get_db_object().commit()

            # Unless configured not to, perform statistics sync
            if self._perform_sync:
                self.po__get_registered_object('statistics_sync').notify()

        # Release lock and remove reference to database object
        self._database.release_db_conn_lock()
        del self._sqlite_object
        self.has_lock = False
        self._database = None
        self.po__unregister_object()

    def get_db_object(self):
        """Return DB object."""
        return self._sqlite_object

    @property
    def cursor(self):
        """Obtain the cursor."""
        if self.has_lock:
            return self.get_db_object().cursor()
        raise DoNotHaveDatabaseConnectionLockError(
            'Do not have database connection lock')


class StatisticsSync(RepeatTimer):
    """Object to perform regular statistics syncronisation between nodes."""

    DEFAULT_TIMEOUT_WAIT_PERIOD = 30
    MAXIMUM_WAIT_PERIOD = 120

    def __init__(self, *args, **kwargs):
        self.original_timer_start = None
        self.last_timer_notify = None
        super(StatisticsSync, self).__init__(*args, **kwargs)

    @property
    def interval(self):
        """Return the timer interval."""
        if self.original_timer_start is None:
            return float(0)

        # If the last timer notify has been increased
        # and has not reached the maximimum timeout
        # period, then re-start the timer for the new
        # notify period
        now = datetime.now()
        new_notify_timeout = (self.last_timer_notify +
                              timedelta(seconds=self.DEFAULT_TIMEOUT_WAIT_PERIOD))
        max_notify_timeout = (self.original_timer_start +
                              timedelta(seconds=self.MAXIMUM_WAIT_PERIOD))
        new_timer_timeout_dt = min(new_notify_timeout, max_notify_timeout)
        if now < new_timer_timeout_dt:
            new_interval = new_timer_timeout_dt - now
            new_interval_seconds = (float(new_interval.seconds) +
                                    (new_interval.microseconds / 1000000.0))
        else:
            new_interval_seconds = float(0)

        return new_interval_seconds

    def notify(self):
        """Notify timer, either start or increasing last notify
        time."""
        # Update last timer notify time
        self.last_timer_notify = datetime.now()

        # If timer has not been set, create it and set the original
        # timer start time
        if self.timer is None:
            self.original_timer_start = datetime.now()
            self.timer = Timer(float(self.DEFAULT_TIMEOUT_WAIT_PERIOD), self.repeat_run)
            self.timer.start()

    def repeat_run(self):
        """Re-start timer once run has complete."""
        # Timer has come to an end...
        # If the thread has been notified, start new timer
        # and return
        new_interval = self.interval
        if new_interval:
            # Start new timer
            self.timer = Timer(new_interval, self.repeat_run)
            self.timer.start()
            return

        # Otherwise, perform sync
        return_output = None
        try:
            # Run command
            return_output = self.run(*self.run_args, **self.run_kwargs)
        except Exception, exc:
            self._log_error(exc)

        self.original_timer_start = None
        self.timer = None
        return return_output

    def run(self):
        """Obtain CPU and memory statistics."""
        Pyro4.current_context.INTERNAL_REQUEST = True
        Syslogger.logger().debug('Starting stats sync')

        self.po__get_registered_object('database_factory').sync()

        Syslogger.logger().debug('Completed stats sync')

        Pyro4.current_context.INTERNAL_REQUEST = False

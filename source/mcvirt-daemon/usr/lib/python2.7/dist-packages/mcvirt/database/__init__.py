"""Module for distributed database across the cluster"""

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

from threading import Lock
import gc
import sqlite3

from mcvirt.rpc.expose_method import Expose
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.exceptions import (DatabaseClassAlreadyInstanciatedError,
                               DoNotHaveDatabaseConnectionLockError,
                               UnableToObtainDatabaseLockError)
from mcvirt.constants import DirectoryLocation
from . import schema_migrations as migrations
from mcvirt.syslogger import Syslogger


class Database(PyroObject):
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
        """Obtain singleton lock and create connection to DB"""
        if not Database.SINGLETON_LOCK.acquire(False):
            raise DatabaseClassAlreadyInstanciatedError(
                'Database class has already been instanciated')

        self._sqlite_object = sqlite3.connect(DirectoryLocation.SQLITE_DATABASE)

    def initialise(self):
        """Perform DB migration"""
        with self.get_locking_connection() as db_inst:
            self._schema_migration(db_inst)

    def __del__(self):
        """On object delection, wait for connection to clear
        and remove sqlite object and singleton lock
        """
        # Remove sqlite object and perform garbage collection
        del self._sqlite_object
        gc.collect()
        Database.SINGLETON_LOCK.release()

    def get_locking_connection(self):
        """Obtain instance of database connection"""
        return DatabaseConnection(self)

    def get_sqlite_object(self):
        """Retrun the SQLite database object"""
        return self._sqlite_object

    @staticmethod
    def obtain_db_conn_lock():
        """Obtain database connection lock"""
        return Database.CONNECTION_LOCK.acquire()

    @staticmethod
    def release_db_conn_lock():
        """Release datbase connection lock"""
        Database.CONNECTION_LOCK.release()

    def _get_schema_version(self, db_inst):
        """Get database schema version"""
        res = db_inst.cursor.execute(
            """SELECT name FROM sqlite_master WHERE type='table' AND name='mcvirt_schema';""")

        # If there is no table for schema
        if res.fetchone() is None:
            return 0

        # Otherwise obtain the schema version from the file
        res = db_inst.cursor.execute(
            """SELECT version FROM mcvirt_schema""")
        version = res.fetchone()
        return version if version is not None else 0

    def _schema_migration(self, db_inst):
        """Perform schema miagrations"""
        Syslogger.logger().info('Performing DB migration')
        schema_version = self._get_schema_version(db_inst)
        Syslogger.logger().info('Current DB schema version: %s' % schema_version)

        if schema_version < 1:
            migrations.v1.migrate(db_inst)

        if schema_version < migrations.SCHEMA_VERSION:
            migrations.update_schema_version(db_inst)


class DatabaseConnection(object):
    """Provide a locking connecftion to the sqlite database object"""

    def __init__(self, database):
        """Obtain the database connection"""
        self.has_lock = False
        self.database = database

    def __enter__(self):
        """Obtain connection lock"""
        if not self.database.obtain_db_conn_lock():
            raise UnableToObtainDatabaseLockError('Unable to obtain database lock')
        self.has_lock = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Release lock"""
        # If an exception was raised, rollback the DB changes
        if exc_type is not None:
            self.database.get_sqlite_object().rollback()

        # Otherwise, commit changes
        else:
            self.database.get_sqlite_object().commit()

        # Release lock and remove reference to database object
        self.database.release_db_conn_lock()
        self.has_lock = False
        self.database = None

    @property
    def cursor(self):
        """Obtain the cursor"""
        if self.has_lock:
            return self.database.get_sqlite_object().cursor()
        raise DoNotHaveDatabaseConnectionLockError(
            'Do not have database connection lock')


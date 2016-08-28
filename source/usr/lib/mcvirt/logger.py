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

from datetime import datetime
import Pyro4

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.syslogger import Syslogger
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.utils import get_hostname


class Logger(PyroObject):

    LOGS = []
    LOGGER = None

    @staticmethod
    def get_logger():
        if Logger.LOGGER is None:
            Logger.LOGGER = Logger()
        return Logger.LOGGER

    @Pyro4.expose()
    def create_log_remote(self, *args, **kwargs):
        """Remotely accessible create_log method"""
        self._get_registered_object('auth').check_user_type('ClusterUser')
        kwargs['local_only'] = True
        log_object = self.create_log(*args, **kwargs)
        self._register_object(log_object)
        return log_object

    def create_log(self, method_name, user, object_name, object_type, node=None, local_only=False):
        """Create a log item and store"""
        if node is None:
            node = get_hostname()

        log_item = LogItem(method_name, user, object_name, object_type, node)
        Logger.LOGS.append(log_item)
        if not local_only and self._is_pyro_initialised:
            def remote_command(remote_node):
                remote_logger = remote_node.get_connection('logger')
                remote_log = remote_logger.create_log_remote(
                    method_name=method_name, user=user, object_name=object_name,
                    object_type=object_type, node=node
                )
                remote_node.annotate_object(remote_log)
                log_item.remote_logs.append(remote_log)
            try:
                cluster = self._get_registered_object('cluster')
                cluster.run_remote_command(remote_command)
            except:
                pass

        return log_item

    @Pyro4.expose()
    def get_logs(self, start_log=None, back=0, newer=False):
        """Return a dict containing log information"""
        if start_log is not None:
            ArgumentValidator.validate_integer(start_log)
        ArgumentValidator.validate_integer(back)
        ArgumentValidator.validate_boolean(newer)

        if start_log is None:
            start_log = len(Logger.LOGS) - 1

        if start_log < 0:
            start_log = 0
        if start_log > (len(Logger.LOGS) - 1):
            start_log = len(Logger.LOGS) - 1

        if back:
            start = 0 if (start_log - back) < 0 else (len(Logger.LOGS) - back)
            finish = start_log + 1
        elif newer:
            start = start_log + 1
            # Length would provide an indicy out of the range,
            # since len(['a']) = 1, but ['a'][1] == error
            # However, this is made up for the fact that range(0, 2) = [0, 1]
            finish = len(Logger.LOGS)
        else:
            # Start at the current log, to return it
            # Finish at current log + 1 as range(1, 2) = [1]
            start = start_log
            finish = start_log + 1

        return_logs = {}
        for itx in range(start, finish):
            if itx < 0:
                continue
            if len(Logger.LOGS) < itx:
                break
            log = Logger.LOGS[itx]
            return_logs[itx] = {
                'start_date': str(log.start_time),
                'status': log.status['status'],
                'status_name': log.status['name'],
                'user': log.user,
                'method': log.method_name,
                'object_name': log.object_name,
                'object_type': log.object_type,
                'description': '%s %s %s' % (log.method_name.capitalize(),
                                             log.object_name,
                                             log.object_type),
                'exception_message': log.exception_message
            }
        return return_logs


class LogState(object):
    """State of log items"""

    QUEUED = {
        'status': 0,
        'name': 'QUEUED'
    }
    RUNNING = {
        'status': 1,
        'name': 'RUNNING'
    }

    SUCCESS = {
        'status': 2,
        'name': 'SUCCESS'
    }
    FAILED = {
        'status': 3,
        'name': 'FAILED'
    }


class LogItem(PyroObject):
    """Log item for storing information about locking command status"""

    def __init__(self, method_name, user, object_name, object_type, node):
        """Create member variables"""
        # Store information about method being run
        self.user = user
        self.object_name = object_name
        self.object_type = object_type
        self.method_name = method_name
        self.remote_logs = []
        self.node = node

        # Store method state
        self.status = LogState.QUEUED
        self.exception_message = None
        self.exception_mcvirt = False

        # Setup date objects for times
        self.queue_time = datetime.now()
        self.start_time = None
        self.finish_time = None
        Syslogger.logger().debug('Queued command: %s' % ', '.join([
            str(self.queue_time), self.user or '', self.object_type or '', self.object_name or '',
            self.method_name or ''
        ]))

    @property
    def description(self):
        pass

    @Pyro4.expose()
    def start(self):
        self.start_time = datetime.now()
        self.status = LogState.RUNNING
        Syslogger.logger().debug('Start command: %s' % ', '.join([
            str(self.start_time), self.user or '', self.object_type or '', self.object_name or '',
            self.method_name or ''
        ]))
        for remote_log in self.remote_logs:
            try:
                remote_log.start()
            except:
                pass

    @Pyro4.expose()
    def finish_success(self):
        self.finish_time = datetime.now()
        self.status = LogState.SUCCESS
        Syslogger.logger().debug('Command complete (success): %s' % ', '.join([
            str(self.finish_time), self.user or '', self.object_type or '', self.object_name or '',
            self.method_name or ''
        ]))
        for remote_log in self.remote_logs:
            remote_log.finish_success()
        self.unregister()

    @Pyro4.expose()
    def finish_error_unknown(self, exception):
        self.finish_time = datetime.now()
        self.status = LogState.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = False
        Syslogger.logger().error('Command failed (Unknown Exception): %s' % ', '.join([
            str(self.finish_time), self.user or '', self.object_type or '', self.object_name or '',
            self.method_name or '', self.exception_message or ''
        ]))
        for remote_log in self.remote_logs:
            try:
                remote_log.finish_error_unknown(str(exception))
            except:
                pass
        self.unregister()

    @Pyro4.expose()
    def finish_error(self, exception):
        self.finish_time = datetime.now()
        self.status = LogState.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = True
        Syslogger.logger().error('Command failed (MCVirt Exception): %s' % ', '.join([
            str(self.finish_time), self.user or '', self.object_type or '', self.object_name or '',
            self.method_name or '', self.exception_message or ''
        ]))
        for remote_log in self.remote_logs:
            try:
                remote_log.finish_error(str(exception))
            except:
                pass
        self.unregister()

    def unregister(self):
        """Unregister connections to remote objects"""
        for log in self.remote_logs:
            try:
                log.unregister()
            except:
                pass
        self.remote_logs = []
        self._unregister_object()

def getLogNames(callback, instance_method, object_type, args, kwargs):
    """Attempts to determine object name and object type, based on method"""
    # Determine if object is a method of an object
    object_name = None

    if instance_method and 'OBJECT_TYPE' in dir(args[0]):
        object_type = object_type if object_type else args[0].OBJECT_TYPE
    elif 'OBJECT_TYPE' in dir(callback.__class__):
        object_type = object_type if object_type else callback.__class__.OBJECT_TYPE
    if instance_method and 'name' in dir(args[0]):
        object_name = args[0].name
    elif 'name' in kwargs:
        object_name = kwargs['name']

    return object_name, object_type

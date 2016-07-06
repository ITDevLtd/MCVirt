"""Provides classes for locking the MCVirt daemon whilst a function is being performed"""
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
from threading import Lock

from mcvirt.exceptions import MCVirtException
from mcvirt.logger import Logger, getLogNames
from mcvirt.syslogger import Syslogger


class MethodLock(object):
    """Class for storing/generating/obtaining a lock object"""

    _lock = None

    @classmethod
    def get_lock(cls):
        """Obtain the lock object and return"""
        if cls._lock is None:
            cls._lock = Lock()
        return cls._lock


def deadlock_escape():
    """Force clear a lock to escape deadlock"""
    lock = MethodLock.get_lock()
    lock.release()


def locking_method(object_type=None, instance_method=True):
    """Provide a decorator method for locking the node whilst performing the method"""
    def wrapper(callback):
        callback.OBJECT_TYPE = wrapper.object_type
        callback.INSTANCE_METHOD = wrapper.instance_method

        def lock_log_and_call(*args, **kwargs):
            # Attempt to obtain object type and name for logging
            object_name, object_type = getLogNames(callback,
                                                   wrapper.instance_method,
                                                   wrapper.object_type,
                                                   args=args,
                                                   kwargs=kwargs)
            lock = MethodLock.get_lock()

            # If the current Pyro connection has the lock, then do not attempt
            # to lock again, as this will be caused by a locking method calling
            # another locking method, which should not attempt to re-obtain the lock
            requires_lock = (not ('has_lock' in dir(Pyro4.current_context) and
                                  Pyro4.current_context.has_lock))

            logger = Logger()
            if 'proxy_user' in dir(Pyro4.current_context) and Pyro4.current_context.proxy_user:
                username = Pyro4.current_context.proxy_user
            elif 'username' in dir(Pyro4.current_context):
                username = Pyro4.current_context.username
            else:
                username = ''
            if requires_lock:
                log = logger.create_log(callback, user=username,
                                        object_name=object_name,
                                        object_type=object_type)
            else:
                log = None

            if requires_lock:
                lock.acquire()
                # @TODO: lock entire cluster - raise exception if it cannot
                # be obtained in short period (~5 seconds)
                Pyro4.current_context.has_lock = True

            if log:
                log.start()
            response = None
            try:
                response = callback(*args, **kwargs)
            except MCVirtException as e:
                Syslogger.logger().error('An internal MCVirt exception occurred in lock')
                Syslogger.logger().error("".join(Pyro4.util.getPyroTraceback()))
                if log:
                    log.finish_error(e)
                if requires_lock:
                    lock.release()
                    Pyro4.current_context.has_lock = False
                raise
            except Exception as e:
                Syslogger.logger().error('Unknown exception occurred in lock')
                Syslogger.logger().error("".join(Pyro4.util.getPyroTraceback()))
                if log:
                    log.finish_error_unknown(e)
                if requires_lock:
                    lock.release()
                    Pyro4.current_context.has_lock = False
                raise
            if log:
                log.finish_success()
            if requires_lock:
                lock.release()
                Pyro4.current_context.has_lock = False
            return response

        return lock_log_and_call

    wrapper.instance_method = instance_method
    wrapper.object_type = object_type
    return wrapper

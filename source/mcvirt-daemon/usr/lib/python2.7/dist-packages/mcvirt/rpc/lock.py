"""Provides classes for locking the MCVirt daemon whilst a function is being performed."""
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
from mcvirt.logger import Logger, get_log_names
from mcvirt.utils import get_hostname
from mcvirt.syslogger import Syslogger


def lock_log_and_call(function_obj):
    """Provide functionality to lock the cluster, log the command
    and then call it
    """
    callback = function_obj.function
    args = [function_obj.obj] + function_obj.nodes[get_hostname()]['args']
    kwargs = function_obj.get_kwargs()
    instance_method = function_obj.instance_method
    object_type = function_obj.object_type

    # Attempt to obtain object type and name for logging
    object_name, object_type = get_log_names(
        callback, instance_method,
        object_type, args=args,
        kwargs=kwargs)

    # If the current Pyro connection has the lock, then do not attempt
    # to lock again, as this will be caused by a locking method calling
    # another locking method, which should not attempt to re-obtain the lock
    requires_lock = (not ('has_lock' in dir(Pyro4.current_context) and
                          Pyro4.current_context.has_lock))

    logger = Logger.get_logger()
    if 'INTERNAL_REQUEST' in dir(Pyro4.current_context) and Pyro4.current_context.INTERNAL_REQUEST:
        username = 'MCVirt Daemon'
    elif 'proxy_user' in dir(Pyro4.current_context) and Pyro4.current_context.proxy_user:
        username = Pyro4.current_context.proxy_user
    elif 'username' in dir(Pyro4.current_context):
        username = Pyro4.current_context.username
    else:
        username = ''
    if requires_lock:
        log = logger.create_log(callback.__name__, user=username,
                                object_name=object_name,
                                object_type=object_type)
    else:
        log = None

    task = None
    if requires_lock:
        if function_obj.po__is_pyro_initialised:
            ts = function_obj.po__get_registered_object('task_scheduler')
            task = ts.add_task(function_obj)

    if log:
        log.start()

    response = None

    try:
        if task is not None:
            response = task.execute()
        else:
            response = callback(*args, **kwargs)

    except MCVirtException as exc:

        Syslogger.logger().error('An internal MCVirt exception occurred in lock')
        Syslogger.logger().error("".join(Pyro4.util.getPyroTraceback()))

        if log:
            log.finish_error(exc)

        # Re-raise exception
        raise

    except Exception as exc:

        Syslogger.logger().error('Unknown exception occurred in lock')
        Syslogger.logger().error("".join(Pyro4.util.getPyroTraceback()))

        if log:
            log.finish_error_unknown(exc)
        raise

    if log:
        log.finish_success()

    return response

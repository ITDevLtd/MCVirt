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

from mcvirt.exceptions import MCVirtException
from mcvirt.logger import Logger, getLogNames
import Pyro4
from threading import Lock

class MethodLock(object):
    _lock = None

    @classmethod
    def getLock(cls):
        if cls._lock is None:
            cls._lock = Lock()
        return cls._lock

class DaemonLock(object):
    pass

def lockingMethod(object_type=None, instance_method=True):
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
            lock = MethodLock.getLock()
            logger = Logger()
            log = logger.create_log(callback, user=Pyro4.current_context.username,
                                    object_name=object_name, object_type=object_type)
            lock.acquire()
            log.start()
            response = None
            try:
                reponse = callback(*args, **kwargs)
            except MCVirtException as e:
                log.finish_error(e)
                lock.release()
                raise
            except Exception as e:
                log.finish_error_unknown(e)
                lock.release()
                raise

            log.finish_success()
            lock.release()
            return response

        return lock_log_and_call

    wrapper.instance_method = instance_method
    wrapper.object_type = object_type
    return wrapper

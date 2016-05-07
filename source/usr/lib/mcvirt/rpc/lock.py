from mcvirt.mcvirt import MCVirtException
from mcvirt.logger import Logger, getLogNames
import Pyro4
from threading import Lock

class MCVirtLock(object):
    _lock = None

    @classmethod
    def getLock(cls):
        if cls._lock is None:
            cls._lock = Lock()
        return cls._lock

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
            lock = MCVirtLock.getLock()
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

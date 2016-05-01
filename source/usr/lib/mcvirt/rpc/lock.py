from mcvirt.mcvirt import MCVirtException
from mcvirt.logger import Logger
import Pyro4
from threading import Lock as ThreadingLock

class Lock(object):
    lock = ThreadingLock()

def lockingMethod(name=None, present=None, past=None):
    def wrapper(callback):
        callback.fun_name = wrapper.fun_name
        callback.present_name = wrapper.present_name
        callback.past_name = wrapper.past_name
        def lock_log_and_call(*args, **kwargs):
            logger = Logger.get_log(callback, Pyro4.current_context.username)
            Lock.lock.acquire()
            try:
                logger.start()
                reponse = callback(*args, **kwargs)
                logger.finish_success()
                Lock.lock.release()
                return response
            except MCVirtException as e:
                logger.finish_error(e)
                Lock.lock.release()
                raise e
            except Exception as e:
                logger.finish_error_unknown(e)
                Lock.lock.release()
                raise e
        return lock_log_and_call
    wrapper.fun_name = name
    wrapper.present_name = present
    wrapper.past_name = past
    return wrapper

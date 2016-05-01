from datetime import datetime
import Pyro4

class Logger(object):

    LOGS = []

    def create_log(self, method, user):
        log_item = LogItem(method, user)
        Logger.LOGS.append(log_item)
        return log_item

    @Pyro4.expose()
    def get_logs(self, start_log=None, back=0, newer=False):
        if start_log is None:
            start_log = len(Logger.LOGS) - 1

        if start_log < 0:
            start_log = 0
        if start_log > len(Logger.LOGS) - 1:
            start_log = len(Logger.LOGS) - 1

        if back:
            start = start_log if (start_log - back) < 0 else back
            finish = start_log
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
                'status': log.status['status'],
                'status_name': log.status['name'],
                'user': log.user,
                'method': log.method.func_name,
                'object_name': log.method.OBJECT_NAME,
                'object_type': log.method.OBJECT_TYPE,
                'description': '%s %s %s' % (log.method.func_name.capitalize(),
                                             log.method.OBJECT_TYPE,
                                             log.method.OBJECT_NAME),
                'exception_message': log.exception_message
            }
        return return_logs


class LogState(object):
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

class LogItem(object):
    def __init__(self, method, user):
        # Store information about method being run
        self.user = user
        self.method = method

        # Store method state
        self.status = LogState.QUEUED
        self.exception_message = None
        self.exception_mcvirt = False

        # Setup date objects for times
        self.queue_time = datetime.now()
        self.start_time = None
        self.finish_time = None

    @property
    def description(self):
        pass

    def start(self):
        self.start_time = datetime.now()
        self.status = LogState.RUNNING

    def finish_success(self):
        self.finish_time = datetime.now()
        self.status = LogState.SUCCESS

    def finish_error_unknown(self, exception):
        self.finish_time = datetime.now()
        self.status = LogState.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = False

    def finish_error(self, exception):
        self.finish_time = datetime.now()
        self.status = LogState.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = True

def getLogNames(callback, instance_method, object_type, args, kwargs):
    """Attempts to determine object name and object type, based on method"""
    # Determine if object is a method of an object
    object_name = None

    if instance_method:
        instance = args[0]
        if 'OBJECT_TYPE' in dir(instance):
            object_type = object_type if object_type else instance.OBJECT_TYPE
        elif 'OBJECT_TYPE' in dir(callback.__class__):
            object_type = object_type if object_type else callback.__class__.OBJECT_TYPE
        if 'name' in dir(instance):
            object_name = instance.name
        elif 'name' in kwargs:
            object_name = kwargs['name']

    return object_name, object_type

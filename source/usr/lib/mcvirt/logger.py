from datetime import datetime
import Pyro4

class Logger(object):

    LOGS = []

    def create_log(self, method, user, object_name, object_type):
        log_item = LogItem(method, user, object_name, object_type)
        Logger.LOGS.append(log_item)
        return log_item

    @Pyro4.expose()
    def get_logs(self, start_log=None, back=0, newer=False):
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
    def __init__(self, method, user, object_name, object_type):
        # Store information about method being run
        self.user = user
        self.method = method
        self.object_name = object_name
        self.object_type = object_type
        self.method_name = method.func_name

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

    if instance_method and 'OBJECT_TYPE' in dir(args[0]):
        object_type = object_type if object_type else args[0].OBJECT_TYPE
    elif 'OBJECT_TYPE' in dir(callback.__class__):
        object_type = object_type if object_type else callback.__class__.OBJECT_TYPE
    if instance_method and 'name' in dir(args[0]):
        object_name = args[0].name
    elif 'name' in kwargs:
        object_name = kwargs['name']

    return object_name, object_type

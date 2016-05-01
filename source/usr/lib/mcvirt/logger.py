from datetime import datetime
from enum import Enum

class Logger(object):

    LOGS = []

    @classmethod
    def get_log(cls, method, user):
        log_item = LogItem(method, user)
        cls.LOGS.append(log_item)
        return log_item

class LogStatus(Enum):
    QUEUED = 0
    RUNNING = 1
    SUCCESS = 2
    FAILED = 3

class LogItem(object):
    def __init__(self, method, user):
        # Store information about method being run
        self.user = user
        self.method = method

        # Store method state
        self.status = LogStatus.QUEUED
        self.exception_message = None
        self.exception_mcvirt = False

        # Setup date objects for times
        self.queue_time = datetime.now()
        self.start_time = None
        self.finish_time = None

    def start(self):
        self.start_time = datetime.now()
        self.status = LogStatus.RUNNING

    def finish_success(self):
        self.finish_time = datetime.now()
        self.status = LogStatus.SUCCESS

    def finish_error_unknown(self, exception):
        self.finish_time = datetime.now()
        self.status = LogStatus.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = False

    def finish_error(self, exception):
        self.finish_time = datetime.now()
        self.status = LogStatus.FAILED
        self.exception_message = str(exception)
        self.exception_mcvirt = True

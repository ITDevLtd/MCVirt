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

from threading import Timer

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.syslogger import Syslogger


class RepeatTimer(PyroObject):
    """Timer that auto-repeats"""

    @property
    def interval(self):
        raise NotImplementedError

    def __init__(self, args=[], kwargs={}, repeat_after_run=True):
        """Create member variables for repeat status and position of restart"""
        self.repeat = True
        self.run_args = args
        self.run_kwargs = kwargs
        self.repeat_after_run = repeat_after_run

    def initialise(self):
        self.timer = Timer(float(self.interval), self.repeat_run)
        self.timer.start()

    def repeat_run(self):
        """Re-start timer once run has complete"""
        Syslogger.logger().error('reat run running')
        if not self.repeat_after_run and self.repeat:
            self.timer.start()
        return_output = self.run(*self.run_args, **self.run_kwargs)
        if self.repeat_after_run and self.repeat:
            self.timer.start()
        return return_output

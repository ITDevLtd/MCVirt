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
    """Timer that auto-repeats."""

    @property
    def interval(self):
        """Method for returning interval for timer."""
        raise NotImplementedError

    def __init__(self, args=None, kwargs=None, repeat_after_run=True):
        """Create member variables for repeat status and position of restart."""
        # State to determine if next run should kick off another timer
        self.repeat = True
        # Timer object
        self.timer = None
        # Store arguments and kwargs for run
        self.run_args = args if args is not None else []
        self.run_kwargs = kwargs if kwargs is not None else {}
        # Determine if next timer is started before or after
        # the actual function is called
        self.repeat_after_run = repeat_after_run

    def initialise(self):
        """Create timer object and start timer."""
        if self.interval and self.interval > 0:
            self.timer = Timer(float(self.interval), self.repeat_run)
            self.timer.start()

    def cancel(self):
        """Cancel timer, if it is running."""
        self.repeat = False
        if self.timer:
            self.timer.cancel()

    def _log_error(self, msg):
        """Log generic error"""
        Syslogger.logger().error(
            'Error ocurred during thread (%s): %s' %
            (self.__class__.__name__, str(msg)))

    def repeat_run(self):
        """Re-start timer once run has complete."""
        # Restart timer, if set to repeat before run
        if not self.repeat_after_run and self.repeat:
            self.timer = Timer(float(self.interval), self.repeat_run)
            self.timer.start()

        return_output = None
        try:
            # Run command
            return_output = self.run(*self.run_args, **self.run_kwargs)
        except Exception, exc:
            self._log_error(exc)

        # Restart timer, if set to repeat after run
        if self.repeat_after_run and self.repeat:
            self.timer = Timer(float(self.interval), self.repeat_run)
            self.timer.start()
        return return_output

    def run(self, *args, **kwargs):
        """Method to run."""
        raise NotImplementedError

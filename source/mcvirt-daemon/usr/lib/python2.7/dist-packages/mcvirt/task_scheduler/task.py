"""Task scheduler, for queuing and managing tasks across the cluster."""

# Copyright (c) 2019 - I.T. Dev Ltd
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

from threading import Event

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname


class Task(PyroObject):
    """Provide an interface for task details and status."""

    @staticmethod
    def get_id_code():
        """Return default Id code for object."""
        return 'ta'

    @property
    def id_(self):
        """Return ID of task"""
        return self._id

    def __init__(self, function_obj):
        """Create member required objects."""
        self._event = Event()
        self._function_obj = function_obj
        self._id = self.generate_id()

    def execute(self):
        """Execute task, which will wait for allocated time"""
        self._event.wait()
        return_val = None
        try:
            return_val = self._function_obj.run()
        except:
            self.on_completion()
            raise
        self.on_completion()
        return return_val

    def on_completion(self):
        """Tear down this task and start next task"""
        task_scheduler = self.po__get_registered_object('task_scheduler')
        task_scheduler.remove_task(self._id, all_nodes=True)
        task_scheduler.next_task()

    def start(self):
        """Signal task start event"""
        self._event.set()


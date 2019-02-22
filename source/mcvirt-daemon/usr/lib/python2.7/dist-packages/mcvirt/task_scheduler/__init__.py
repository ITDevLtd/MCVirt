"""Task scheduler, for queuing and managing tasks across the cluster."""

# Copyright (c) 2014 - I.T. Dev Ltd
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

    def __init__(self, id_=None, node=None, remote=False):
        """Create member required objects."""
        # Only 
        self._event = Event() if remote is False else None
        self._id = id_ if id_ is not None else self.generate_id()
        self._node = node if node is not None else get_hostname()

    def start(self):
        """Signal task start event"""
        self._event.set()


class TaskScheduler(PyroObject):
    """Manage tasks and provide queuing and locking."""

    _TASK_QUEUE = []

    def add_task(self):
        """Add task to queue."""
        task = Task()
        self.distribute_task(task)

    def distribute_task(self, task):
        """Distribute task to cluster."""

    def receive_task(self, node, task_id):
        """Create task object from 

    def remote_notify(self, task_id):
        """Allow a remote node to notify a task to start"""

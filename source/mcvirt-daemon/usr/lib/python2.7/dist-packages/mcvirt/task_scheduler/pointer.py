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
from mcvirt.rpc.expose_method import Expose
from mcvirt.utils import get_hostname


class TaskPointer(PyroObject):
    """Provide a pointer to a task, which is distributed to all nodes in cluster"""

    @staticmethod
    def get_id_code():
        """Return default Id code for object."""
        return 'ta'

    @property
    def task_id(self):
        """Obtain task ID"""
        return self._task_id

    def __init__(self, task_id, node=None):
        """Create member required objects."""
        self._task_id = task_id
        self._node = node
        self._provisional = True
        self._cancelled = False

    @Expose()
    def get_task(self):
        """Obtain remote task object"""
        remote_task_scheduler, node_obj = self.po__get_registered_object(
            'task_scheduler').get_remote_object(
                node=self._node,
                return_node_object=True)

        remote_task = remote_task_scheduler.get_task_by_id(self._task_id)
        node_obj.annotate_object(remote_task)
        return remote_task

    def is_cancelled(self):
        """Return whether task is cancelled"""
        return self._cancelled

    @Expose(remote_nodes=True)
    def cancel(self):
        """Set task as cancelled"""
        self._cancelled = True

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the group object on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_task_scheduler = node_object.get_connection('task_scheduler')
        remote_task_pointer = remote_task_scheduler.get_task_pointer_by_id(self._task_id)
        node_object.annotate_object(remote_task_pointer)

        return remote_task_pointer

    def confirm(self):
        """Confirm task as being agreed with all nodes"""
        self._provisional = False

    @Expose()
    def start(self):
        """Get the task on the remote and start the task"""
        if self._node == get_hostname():
            self.po__get_registered_object('task_scheduler').get_task_by_id(
                self._task_id).start()
        else:
            self.get_remote_object(self._node).start()

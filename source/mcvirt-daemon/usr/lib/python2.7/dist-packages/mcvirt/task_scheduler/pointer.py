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
from mcvirt.syslogger import Syslogger


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

    @property
    def execution_node(self):
        """Obtain execution node"""
        return self._execution_node

    @property
    def is_provisional(self):
        return self._provisional

    @property
    def is_cancelled(self):
        """Return whether task is cancelled"""
        return self._cancelled

    def __init__(self, task_id, execution_node=None):
        """Create member required objects."""
        self._task_id = task_id
        self._execution_node = execution_node
        self._is_local = (execution_node == get_hostname())
        self._provisional = True
        self._cancelled = False

    def get_task(self):
        """Obtain remote task object"""
        task_scheduler = self.po__get_registered_object(
            'task_scheduler')
        node_obj = None

        # If not local, use task_scheduler to obtain remote task scheduler
        if not self._is_local:
            task_scheduler, node_obj = task_scheduler.get_remote_object(
                node=self._execution_node,
                return_node_object=True)
        task = task_scheduler.get_task_by_id(self.task_id)

        # Annotate remote object
        if not self._is_local:
            node_obj.annotate_object(task)

        return task

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
        Syslogger.logger().error('TASK ID: %s' % str(self.task_id))
        remote_task_pointer = remote_task_scheduler.get_task_pointer_by_id(self.task_id)
        Syslogger.logger().error('remote task: %s' % str(remote_task_pointer))
        node_object.annotate_object(remote_task_pointer)

        return remote_task_pointer

    def confirm(self):
        """Confirm task as being agreed with all nodes"""
        self._provisional = False

    @Expose()
    def start(self):
        """Get the task on the remote and start the task"""
        self.get_task().start()

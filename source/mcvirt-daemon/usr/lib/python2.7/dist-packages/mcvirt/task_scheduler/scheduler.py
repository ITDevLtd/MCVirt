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

from time import sleep
from random import randrange

import Pyro4

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname
from mcvirt.task_scheduler.task import Task
from mcvirt.task_scheduler.pointer import TaskPointer
from mcvirt.rpc.expose_method import Expose
from mcvirt.syslogger import Syslogger
from mcvirt.exceptions import TaskSchedulerConflictError


class TaskScheduler(PyroObject):
    """Manage tasks and provide queuing and locking."""

    _TASK_QUEUE = []
    _TASK_POINTERS = {}
    _TASKS = {}

    TASK_DISTRIBUTE_ATTEMPTS = 5
    MIN_NEGOTIATE_WAIT_TIME = 5
    MAX_NEGOTIATE_WAIT_TIME = 200

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None,   # Otherwise, pass a remote node connection
                          return_node_object=False):
        """Obtain an instance of task scheduler on a remote node."""
        cluster = self.po__get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        remote_task_scheduler = node_object.get_connection('task_scheduler')
        if return_node_object:
            return remote_task_scheduler, node_object
        return remote_task_scheduler

    @Expose(remote_nodes=True)
    def get_task_by_id(self, task_id):
        if task_id in TaskScheduler._TASKS:
            return TaskScheduler._TASKS[task_id]
        return None

    @Expose()
    def get_task_pointer_by_id(self, task_id):
        if task_id in TaskScheduler._TASK_POINTERS:
            return TaskScheduler._TASK_POINTERS[task_id]
        return None

    def get_current_task(self):
        """Get the current task"""
        return self.po__get_current_context_item('CURRENT_TASK')

    def is_task_cancelled(self, task_id):
        """Return if a task is cancelled"""
        return TaskScheduler._TASK_POINTERS[task_id].is_cancelled()

    def get_current_task_pointer(self):
        """Get the current task"""
        return self.po__get_current_context_item('CURRENT_TASK_P')

    @Expose(remote_nodes=True)
    def confirm_task_pointer(self, task_id):
        """Confirm task pointer from given task"""
        TaskScheduler._TASK_POINTERS[task_id].confirm()

    def add_task(self, function_obj):
        """Add task to queue."""
        task = Task(function_obj)

        # Register task and add to dict of tasks
        self.po__register_object(task)
        self._TASKS[task.id_] = task

        previous_id = False
        # Attempt to get a concensus on a queue position
        # for the new task
        for _ in range(self.TASK_DISTRIBUTE_ATTEMPTS):
            previous_id = self.distribute_task(task)
            if previous_id is not False:
                break

            # Sleep for random time
            sleep(
                (1.0/1000) *
                randrange(
                    TaskScheduler.MIN_NEGOTIATE_WAIT_TIME,
                    TaskScheduler.MAX_NEGOTIATE_WAIT_TIME
                )
            )

        else:
            raise TaskSchedulerConflictError(
                'Unable to successfully distribute task without conflict')

        # Since the task is now confirmed on the queue,
        #  remove provisional tag
        self.confirm_task_pointer(task.id_, all_nodes=True)

        # If thre previous task ID is None,
        # then the task can be immediately executed,
        # since no other task will need executing
        if previous_id is None:
            self.get_task_pointer_by_id(task.id_).start()

        return task

    def distribute_task(self, task):
        """Distribute task to cluster."""
        # Create a pointer, add to stack, push to cluster
        latest_id = self.get_latest_task_id()
        dist_status = self.receive_task(
            node=get_hostname(),
            task_id=task.id_, latest_task_id=latest_id,
            all_nodes=True, return_dict=True)

        # Get all successful nodes
        s_nodes = []
        f_nodes = 0
        Syslogger.logger().debug(dist_status)
        Syslogger.logger().debug(latest_id)
        for node_name in dist_status:
            if dist_status[node_name] is False:
                f_nodes += 1
            else:
                s_nodes.append(node_name)

        # If any nodes failed, revert
        if f_nodes:
            self.remove_task(nodes=s_nodes, task_id=task.id_)
            return False

        return latest_id

    @Expose(remote_nodes=True)
    def receive_task(self, node, task_id, latest_task_id):
        """Create task object from """
        # If the latest task does not match the other nodes latest
        # task, then return False as a conflict occured
        if self.get_latest_task_id() != latest_task_id:
            return False

        # Create task pointer and add to task queue and
        # task pointer lookup
        task_pointer = TaskPointer(task_id=task_id, node=node)
        self.po__register_object(task_pointer)
        TaskScheduler._TASK_QUEUE.append(task_pointer)
        TaskScheduler._TASK_POINTERS[task_id] = task_pointer
        return True

    @Expose(remote_nodes=True)
    def remove_task(self, task_id):
        """Remove task from queues, lookup tables and unregister
        from daemon"""
        # If the task exists, then remove from task queue,
        # task lookup and unregister from pyro
        if task_id in TaskScheduler._TASK_POINTERS:
            task_pointer = TaskScheduler._TASK_POINTERS[task_id]
            TaskScheduler._TASK_QUEUE.remove(task_pointer)
            self.po__unregister_object(obj=task_pointer)

            # Remove the task pointer from list
            del TaskScheduler._TASK_POINTERS[task_id]

        # If the task is present on this node, remove it
        if task_id in TaskScheduler._TASKS:
            self.po__unregister_object(obj=TaskScheduler._TASKS[task_id])
            del TaskScheduler._TASKS[task_id]

    @Expose()
    def get_latest_task_id(self):
        """Obtain the ID of the latest task in the queue.
        If therre are no takss in the queue, return None.
        """
        task_p = self.get_current_running_task_pointer()
        if task_p:
            return task_p.task_id
        return None

    def get_current_running_task_pointer(self):
        """Get current running task"""
        for task in TaskScheduler._TASK_QUEUE:
            if not task.is_cancelled():
                return task
        return None

    @Expose()
    def cancel_current_task(self):
        """Cancel the current running task"""
        task_p = self.get_current_running_task_pointer()
        if task_p:
            task_p.cancel(all_nodes=True)

            # Start next task
            self.next_task()

            # Return True indicating that task has
            # been cancelled
            return True

        # No task has been cancelled
        return False

    def next_task(self):
        """Allow a remote node to notify a task to start"""
        task = self.get_current_running_task_pointer()
        if task:
            task.start()

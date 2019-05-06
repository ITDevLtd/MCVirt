"""Provide interface for RPC to cluster nodes."""

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

from threading import Lock

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.syslogger import syslogger


class ClusterLock(PyroObject):
    """A class to perform remote commands on MCVirt nodes."""

    CLUSTER_LOCK_INSTANCE = None
    LOCK_INSTANCE = None

    def initalise(self):
        """On node startup, create local reference to singleton instance."""
        if ClusterLock.CLUSTER_LOCK_INSTANCE is None:
            ClusterLock.CLUSTER_LOCK_INSTANCE = self

        if ClusterLock.LOCK_INSTANCE is None:
            ClusterLock.LOCK_INSTANCE = Lock()

    def __init__(self):
        """Initialise a blank array of nodes that have been locked."""
        self.nodes = []

    def __enter__(self):
        """Attempt to lock cluster."""
        if ClusterLock.LOCK_INSTANCE is None:
            raise Exception('Lock object not present')

        cluster_object = None
        # Detmine if current object is registered
        if self.po__is_pyro_initialised:
            cluster_object = self.po__get_registered_object('cluster')

        elif ClusterLock.CLUSTER_LOCK_INSTANCE is not None:
            # If not initialised, determine if
            # singleton is stored in class attribute
            cluster_object = ClusterLock.CLUSTER_LOCK_INSTANCE.po__get_registered_object('cluster')

        else:
            # If there is no way to obtain a
            # pyro-initialised varient of this object,
            # default to just locking the local node
            self.lock_node()
            Syslogger.logger().warn(
                ('Unable to obtain pyro-initialised lock object, '
                 'just locking local node'))
            return

            self.locked_nodes = self.lock_node(all_nodes=True).keys()

    def __exit__(self, exc_type, exc_value, traceback):
        """Unlock cluster."""
        self.unlock_node(nodes=self.locked_nodes)

    @Expose(remote_nodes=True, undo_method='unlock_node')
    def lock_node(self):
        """Attempt to lock local node."""
        # Aquire lock
        return ClusterLock.LOCK_INSTANCE.acquire(False)

    @Expose()
    def unlock_node(self):
        """Remove held lock on local node."""
        # Release lock object
        ClusterLock.LOCK_INSTANCE.release()

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

    def lock(self):
        """Attempt to lock cluster."""
        pass

    def unlock(self):
        """Unlock cluster."""
        pass

    @Expose()
    def lock_node(self):
        """Attempt to lock local node."""
        pass

    @Expose()
    def unlock_node(self):
        """Remove held lock on local node."""
        pass

"""Base class for providing Pyro-based methods for objects"""
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

import Pyro4


class PyroObject(object):
    """Base class for providing Pyro-based methods for objects"""

    @property
    def _is_pyro_initialised(self):
        """Determine if object is registered with the Pyro deamon"""
        return ('_pyroDaemon' in self.__dict__.keys())

    @property
    def _cluster_disabled(self):
        """Determine if the cluster has been actively disabled"""
        # @TODO Implement this using Pyro annotations and current_context
        if self._is_pyro_initialised and 'ignore_cluster' in dir(Pyro4.current_context):
            return Pyro4.current_context.ignore_cluster
        else:
            return False

    @property
    def _ignore_drbd(self):
        """Determine if DRBD statuses are being actively ignored"""
        if self._is_pyro_initialised and 'ignore_drbd' in dir(Pyro4.current_context):
            return Pyro4.current_context.ignore_drbd
        else:
            return False

    @property
    def _is_cluster_master(self):
        """Determine if the local node is acting as cluster master for the command"""
        if self._is_pyro_initialised and 'cluster_master' in dir(Pyro4.current_context):
            return Pyro4.current_context.cluster_master
        else:
            return True

    def _register_object(self, local_object):
        """Register an object with the pyro daemon"""
        if self._is_pyro_initialised:
            self._pyroDaemon.register(local_object)

    def _convert_remote_object(self, remote_object):
        """Return a local instance of a remote object"""
        # Ensure that object is a remote object
        if self._is_pyro_initialised and '_pyroUri' in dir(remote_object):
            # Obtain daemon instance of object
            return self._pyroDaemon.objectsById[remote_object._pyroUri.object]
        return remote_object

    def _get_registered_object(self, object_name):
        """Return objects registered in the Pyro Daemon"""
        if self._is_pyro_initialised and object_name in self._pyroDaemon.registered_factories:
            return self._pyroDaemon.registered_factories[object_name]
        else:
            return None

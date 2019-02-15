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

import hashlib
import datetime
import Pyro4
from threading import Lock

from mcvirt.exceptions import MCVirtException
from mcvirt.syslogger import Syslogger


class PyroObject(object):
    """Base class for providing Pyro-based methods for objects"""

    def initialise(self):
        """Method to override, which is run once all factory objects
        have been added to the daemon
        """
        pass

    @staticmethod
    def get_id_name_checksum_length():
        """Return the lenght of the name checksum to use in the ID"""
        return 18

    @staticmethod
    def get_id_date_checksum_length():
        """Return the lenght of the name checksum to use in the ID"""
        return 22

    @staticmethod
    def get_id_code():
        """Return default Id code for object - should be overriden"""
        return 'po'

    @classmethod
    def generate_id(cls, name):
        """Generate ID for group"""
        # Generate sha sum of name and sha sum of
        # current datetime
        name_checksum = hashlib.sha512(name).hexdigest()
        date_checksum = hashlib.sha512(str(datetime.datetime.now())).hexdigest()
        return '%s-%s-%s' % (
            cls.get_id_code(),
            name_checksum[0:cls.get_id_name_checksum_length()],
            date_checksum[0:cls.get_id_date_checksum_length()])

    @property
    def convert_to_remote_object_in_args(self):
        """Whether the expose method (or transaction object) converts
        the object to a remote object if has been passed into a
        method of an exposed object to run on remote nodes
        """
        return True

    @property
    def _is_pyro_initialised(self):
        """Determine if object is registered with the Pyro deamon"""
        return '_pyroDaemon' in self.__dict__.keys()

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

    @property
    def _has_lock(self):
        """Determine if the current session holds the global lock"""
        if self._is_pyro_initialised and 'has_lock' in dir(Pyro4.current_context):
            return Pyro4.current_context.has_lock
        else:
            # If not defined, assume that we do not have the lock
            return False

    def _register_object(self, local_object, debug=True):
        """Register an object with the pyro daemon"""
        return_value = False
        if self._is_pyro_initialised:
            try:
                if debug:
                    Syslogger.logger().debug('Registering object (dynamic): %s' % local_object)
            except Exception:
                pass
            self._pyroDaemon.register(local_object)
            return_value = True

        if '_pyro_server_ref' in dir(self):
            local_object._pyro_server_ref = self._pyro_server_ref

        return return_value

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
        elif ('_pyro_server_ref' in dir(self) and
                object_name in self._pyro_server_ref.registered_factories):
            return self._pyro_server_ref.registered_factories[object_name]
        else:
            return None

    def unregister_object(self, obj=None, debug=True):
        """Unregister object from the Pyro Daemon"""
        if self._is_pyro_initialised:
            if obj is None:
                obj = self
            try:
                if debug:
                    Syslogger.logger().debug('Unregistering object (dynamic): %s' % obj)
            except Exception:
                pass

            # Unregister object from pyro
            self._pyroDaemon.unregister(obj)

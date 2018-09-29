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

from mcvirt.rpc.lock import lock_log_and_call


class Expose(object):
    """Decorator for exposing method via Pyro and optional log and locking"""
    # @TODO Add permission checking, which is only performed during
    #       pyro call to method

    SESSION_OBJECT = None

    def __init__(self, locking=False, object_type=None, instance_method=None, only_cluster=False):
        """Setup variables passed in via decorator as member variables"""
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.only_cluster = only_cluster

    def __call__(expose_self, callback):
        """Run when object is created. The returned value is the method that is executed"""
        def inner(*args, **kwargs):
            """Run when the wrapping method is called"""
            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Renew session expiry
                Expose.SESSION_OBJECT.USER_SESSIONS[
                    Expose.SESSION_OBJECT._get_session_id()
                ].disable()
            if expose_self.locking:
                return_value = lock_log_and_call(callback, args, kwargs,
                                                 expose_self.instance_method,
                                                 expose_self.object_type)
            else:
                return_value = callback(*args, **kwargs)

            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Renew session expiry
                Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].renew()

            return return_value

        def exposed_method(self, *args, **kwargs):
            """Performs functionality/checks that are
            only performed whilst being called through Pyro
            """
            # If configured to only run if the user is a cluster user, then
            # assert this.
            if expose_self.only_cluster:
                self._get_registered_object('auth').assert_user_type('ClusterUser')

            return inner(self, *args, **kwargs)

        # Expose the function
        return Pyro4.expose(inner)


class RunRemoteNodes(object):
    """Experimental decorator to allow running a set of commands on a remote node without
       adding boiler plate code to execute the function on the remote nodes"""

    def __call__(self, callback):
        """Overriding method, which executes on remote command"""
        def inner(self, *args, **kwargs):
            """Run when the actual wrapping method is called"""
            # Obtain the list of nodes from kwargs, if defined
            if 'nodes' in kwargs:
                nodes = list(kwargs['nodes'])
                # Remove from arguments
                del kwargs['nodes']

                # If return_dict has been specified, obtain variable
                # and remove from kwargs
                return_dict = False
                if 'return_dict' in kwargs:
                    return_dict = kwargs['return_dict']
                    del kwargs['return_dict']

                # Setup empty return value, incase localhost is not in the list
                # of nodes
                return_val = {} if return_dict else None

                # Determine if local node is present in list of nodes.
                cluster = self._get_registered_object('cluster')
                local_hostname = cluster.get_local_hostname()
                if local_hostname in nodes:
                    # If so, remove node from list, run the local callback first
                    # and capture the output
                    nodes.remove(local_hostname)
                    response = callback(self, *args, **kwargs)
                    if return_dict:
                        return_val[local_hostname] = response
                    else:
                        return_val = response

                # Iterate over remote nodes, obtain the remote object
                # and executing the function
                for node in nodes:
                    remote_object = self.get_remote_object(node=node)

                    # Run the method by obtaining the member attribute, based on the name of
                    # the callback function from of the remote object
                    response = getattr(remote_object, callback.__name__)(*args, **kwargs)

                    # Add output to return_val if return_dict was specified
                    if return_dict:
                        return_val[node] = response

                # Return the returned value from the local callback
                return return_val

            # Otherwise, if ndoes not defined, call method as normal
            else:
                return callback(self, *args, **kwargs)

        return inner

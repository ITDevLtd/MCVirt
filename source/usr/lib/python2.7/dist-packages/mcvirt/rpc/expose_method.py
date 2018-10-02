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
from mcvirt.utils import get_hostname


class Transaction(object):
    """Perform a saga-transaction, allowing functions
    that make system mofications, the ability to be rolled
    back.
    """

    # Static list of current transactions
    transactions = []

    @classmethod
    def in_transaction(cls):
        """Determine if a transaction is currently in progress"""
        return len(cls.transactions) > 0

    def __init__(self):
        """Setup member variables and register transaction"""
        # Determine transaction ID.
        self._transaction_id = len(Transaction.transactions)

        # Initialise empty list of functions
        self.functions = []

        # Add the transaction to the static list of transactions
        Transaction.transactions.append(self)

    def finish_transaction(self):
        """Mark the transaction as having been completed"""
        # Delete each of the function objects
        for func in self.functions:
            self.functions.remove(func)

        # Remove the transaction object from the global list
        Transaction.transactions.remove(self)

    @classmethod
    def register_function(cls, function):
        """Register a function with the current transactions"""
        # Only register function if a transaction is in progress
        if cls.in_transaction():
            # Append the function to the newest transaction
            Transaction.transactions[-1].functions.append(function)

    @classmethod
    def function_failed(cls, function):
        """Called when a function fails - perform
        the undo method on all previous functions on each of the
        transactions
        """
        # If in a transaction
        if cls.in_transaction():
            # Iterate through transactions, removing each item
            for transaction_ar in reversed(cls.transactions):
                # Iteracte through each function in the transaction
                for function in reversed(transaction_ar.functions):

                    # Undo the function
                    function.undo()

                # Mark the transaction as complete, removing
                # it from global list and all functions
                transaction_ar.finish_transaction()
        else:
            # Otherwise, undo single function
            function.undo()


class Function(object):
    """Provide an interface for a function call, storing
    the function and parameters passed in, as well as
    executing the function
    """

    def __init__(self, function, obj, args, kwargs,
                 locking, object_type, instance_method):
        """Store the original function, instance and arguments
        as member variables for the function call and undo method
        """
        # Stored list of nodes for command to be run on, if passed
        # and remove from kwargs
        if 'nodes' in kwargs:
            self.nodes = kwargs['nodes']
            del kwargs['nodes']
        # Otherwise, just add the local node
        else:
            self.nodes = [get_hostname()]

        # If return_dict has been specified, obtain variable
        # and remove from kwargs
        self.return_dict = False
        if 'return_dict' in kwargs:
            self.return_dict = kwargs['return_dict']
            del kwargs['return_dict']

        # Setup status for command on each node
        self.node_status = {
            node: {'complete': False,
                   'return_val': None}
            for node in self.nodes
        }

        # Store function and parameters
        self.function = function
        self.obj = obj
        self.args = args
        self.kwargs = kwargs
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.is_complete = False

    def run(self):
        """Run the function"""
        # If the machine is the cluster master, run
        # the fuction with the transaction abilities
        if self.obj._is_cluster_master:
            self._register_and_call()

        # Otherwise, run the function normally,
        # as only the cluster master deals with
        # transactions
        else:
            self._call_function_local()

        # Return the data from the function
        return self._get_response_data()

    def _register_and_call(self):
        """Run the function, catching any exceptions
        and calling the roll back
        """
        # Register commnad with transaction
        Transaction.register_function(self)

        try:
            # Run function
            self._call_function_local()

        # Catch all exceptions
        except:
            # Notify that the transaction that the functino has failed
            Transaction.function_failed(self)

            # Re-throw the error
            raise

    def _call_function_local(self):
        """Perform the actual command on the local node"""
        # If locking was defined, perform command with
        # log lock and call
        if self.locking:
            self.node_status[get_hostname()]['return_val'] = \
                lock_log_and_call(self.function,
                                  [self.obj] + self.args,
                                  self.kwargs,
                                  self.instance_method,
                                  self.object_type)

        # Otherwise run the command directly
        else:
            self.node_status[get_hostname()]['return_val'] = \
                self.function(self.obj, _f=self, *self.args, **self.kwargs)

    def _call_function_remote(self, node):
        """Run the function on a remote node"""
        # Obtain the remote object
        remote_object = self.obj.get_remote_object(node=node)

        # Run the method by obtaining the member attribute, based on the name of
        # the callback function from of the remote object
        response = getattr(remote_object, self.function.__name__)(*self.args, **self.kwargs)

        # Store output in response
        self.node_status[node]['return_val'] = response

    def _get_response_data(self):
        """Determine and return response data"""
        # Return dict of node -> output, if a dict response was
        # specified
        if self.return_dict:
            return {node: self.node_status[node]['return_val']
                    for node in self.nodes}

        # Otherwise, default to returning data from local node
        elif get_hostname() in self.nodes:
            return self.node_status[get_hostname()]['return_val']

        # Otherwise, return the response from the first found node.
        elif self.node_status:
            return self.node_status[self.node_status.keys()[0]]['return_val']

        # Otherwise, if no node data, return None
        return None

    def add_undo_argument(self, **kwargs):
        """Add an additional keyword argument to be
        passed to the undo method, when it is run
        """
        self.kwargs.update(kwargs)

    def complete(self):
        """Mark the function as having completed
        successfully. Once run, if any exception occurs within
        the function (or, if in one, the rest of the transaction),
        the undo method will be called
        """
        self.is_complete = True

    def undo(self):
        """Execute the undo method for the function"""
        undo_function_name = 'undo__%s' % self.function.__name__
        if self.is_complete and hasattr(self.obj, undo_function_name):
            getattr(self.obj, undo_function_name)(*self.args, **self.kwargs)


class Expose(object):
    """Decorator for exposing method via Pyro and optional log and locking"""
    # @TODO Add permission checking, which is only performed during
    #       pyro call to method

    SESSION_OBJECT = None

    def __init__(self, locking=False, object_type=None, instance_method=None):
        """Setup variables passed in via decorator as member variables"""
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method

    def __call__(self, callback):
        """Run when object is created. The returned value is the method that is executed"""
        def inner(self_obj, *args, **kwargs):
            """Run when the wrapping method is called"""
            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Disable the expiration whilst the method runs
                Expose.SESSION_OBJECT.USER_SESSIONS[
                    Expose.SESSION_OBJECT._get_session_id()
                ].disable()

            # Try-catch main method, to ensure that
            # the session is always renewed (and re-enabled)
            try:

                # Create function object and run
                function = Function(function=callback, obj=self_obj,
                                    args=args, kwargs=kwargs,
                                    locking=self.locking,
                                    object_type=self.object_type,
                                    instance_method=self.instance_method)
                return_value =  function.run()

            except:
                # Determine if session ID is present in current context and the session object has
                # been set
                if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                    # Renew session expiry
                    Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].renew()

                # Reraise exception
                raise

            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Renew session expiry
                Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].renew()

            return return_value
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


                # Setup empty return value, incase localhost is not in the list
                # of nodes
                return_val = {} if return_dict else None

                # Determine if local node is present in list of nodes.
                local_hostname = get_hostname()
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

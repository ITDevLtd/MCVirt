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
            nodes = kwargs['nodes']
            del kwargs['nodes']
        # Otherwise, just add the local node
        else:
            nodes = [get_hostname()]

        # If return_dict has been specified, obtain variable
        # and remove from kwargs
        self.return_dict = False
        if 'return_dict' in kwargs:
            self.return_dict = kwargs['return_dict']
            del kwargs['return_dict']

        # Setup status for command on each node
        self.nodes = {
            node: {'complete': False,
                   'return_val': None,
                   'kwargs': dict(kwargs),
                   'args': list(args)}
            for node in nodes
        }
        self.current_node = None

        # Store function and parameters
        self.function = function
        self.obj = obj
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.is_complete = False

        # Register instance and functions with pyro
        self.obj._register_object(self)
        Pyro4.expose(self.add_undo_argument)
        Pyro4.expose(self.complete)

    def run(self):
        """Run the function"""
        # Pause the session timeout
        self._pause_user_session()

        # Catch all exceptions to ensure that user
        # session is always reset
        try:
            # If the local host is in the list of nodes
            # run the function on the local node first
            if get_hostname() in self.nodes:
                # If the machine is the cluster master, run
                # the fuction with the transaction abilities
                if self.obj._is_cluster_master:
                    self._register_and_call()

                # Otherwise, run the function normally,
                # as only the cluster master deals with
                # transactions
                else:
                    self._call_function_local()

        except:
            # Reset user session after the command is
            # complete
            self._reset_user_session()

            # Re-raise exception
            raise

        # Reset user session after the command is
        # complete
        self._reset_user_session()

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
        # Set the current node to the local node
        local_hostname = get_hostname()
        self.current_node = local_hostname

        # If locking was defined, perform command with
        # log lock and call
        if self.locking:
            # Create list of kwargs with local object
            kwargs = dict(self.nodes[local_hostname]['kwargs'])
            kwargs['_f'] = self
            self.nodes[local_hostname]['return_val'] = \
                lock_log_and_call(self.function,
                                  [self.obj] + self.nodes[local_hostname]['args'],
                                  kwargs,
                                  self.instance_method,
                                  self.object_type)

        # Otherwise run the command directly
        else:
            self.nodes[local_hostname]['return_val'] = \
                self.function(self.obj, _f=self, *self.nodes[local_hostname]['args'],
                              **self.nodes[local_hostname]['kwargs'])

    def _call_function_remote(self, node):
        """Run the function on a remote node"""
        # Set current node to remote node
        self.current_node = node

        # Obtain the remote object
        remote_object = self.obj.get_remote_object(node=node)

        # Create kwargs including local object
        kwargs = dict(self.nodes[node]['kwargs'])
        kwargs['_k'] = self

        # Run the method by obtaining the member attribute, based on the name of
        # the callback function from of the remote object
        response = getattr(remote_object, self.function.__name__)(
            *self.nodes[node]['args'], **kwargs)

        # Store output in response
        self.nodes[node]['return_val'] = response

    def _get_response_data(self):
        """Determine and return response data"""
        # Return dict of node -> output, if a dict response was
        # specified
        if self.return_dict:
            return {node: self.nodes[node]['return_val']
                    for node in self.nodes.keys()}

        # Otherwise, default to returning data from local node
        elif get_hostname() in self.nodes:
            return self.nodes[get_hostname()]['return_val']

        # Otherwise, return the response from the first found node.
        elif self.nodes:
            return self.nodes[self.nodes.keys()[0]]['return_val']

        # Otherwise, if no node data, return None
        return None

    def add_undo_argument(self, **kwargs):
        """Add an additional keyword argument to be
        passed to the undo method, when it is run
        """
        self.nodes[self.current_node]['kwargs'].update(kwargs)

    def complete(self):
        """Mark the function as having completed
        successfully. Once run, if any exception occurs within
        the function (or, if in one, the rest of the transaction),
        the undo method will be called
        """
        self.nodes[self.current_node]['complete'] = True

    def undo(self):
        """Execute the undo method for the function"""
        undo_function_name = 'undo__%s' % self.function.__name__
        if self.is_complete and hasattr(self.obj, undo_function_name):
            getattr(self.obj, undo_function_name)(*self.args, **self.kwargs)

    def _pause_user_session(self):
        """Pause the user session"""
        # Determine if session ID is present in current context and the session object has
        # been set
        if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
            # Disable the expiration whilst the method runs
            Expose.SESSION_OBJECT.USER_SESSIONS[
                Expose.SESSION_OBJECT._get_session_id()
            ].disable()

    def _reset_user_session(self):
        """Reset the user session"""
        # Determine if session ID is present in current context and the session object has
        # been set
        if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
            # Renew session expiry
            Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].renew()


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

            # Create function object and run
            function = Function(function=callback, obj=self_obj,
                                args=args, kwargs=kwargs,
                                locking=self.locking,
                                object_type=self.object_type,
                                instance_method=self.instance_method)
            return function.run()

        # Expose the function
        return Pyro4.expose(inner)

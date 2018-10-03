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

from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.lock import lock_log_and_call
from mcvirt.utils import get_hostname
from mcvirt.syslogger import Syslogger


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
        self.complete = False

        # Add the transaction to the static list of transactions
        Transaction.transactions.insert(0, self)

    def finish_transaction(self):
        """Mark the transaction as having been completed"""
        self.comlpete = True
        # Only remove transaction if it is the last
        # transaction in the stack
        if Transaction.transactions.index(self) == 0:
            Syslogger.logger().debug('End of transaction stack')

            # Tear down all transactions
            for transaction in Transaction.transactions:
                # Delete each of the function objects
                for func in self.functions:
                    self.functions.remove(func)
                    func.unregister(force=True)
                    del func

            # Reset list of transactions
            Transaction.transactions = []

    @classmethod
    def register_function(cls, function):
        """Register a function with the current transactions"""
        # Only register function if a transaction is in progress
        if cls.in_transaction():
            for transaction in Transaction.transactions:
                # Append function to transaction, if it is
                # not marked as complete
                if not transaction.complete:
                    # Append the function to the newest transaction
                    transaction.functions.insert(0, function)

    @classmethod
    def function_failed(cls, function):
        """Called when a function fails - perform
        the undo method on all previous functions on each of the
        transactions
        """
        # If in a transaction
        if cls.in_transaction():
            # Iterate through transactions, removing each item
            for transaction_ar in cls.transactions:
                # Iteracte through each function in the transaction
                for function in transaction_ar.functions:

                    # Undo the function
                    function.undo()

                # Mark the transaction as complete, removing
                # it from global list and all functions
                transaction_ar.finish_transaction()
        else:
            # Otherwise, undo single function
            function.undo()


class Function(PyroObject):
    """Provide an interface for a function call, storing
    the function and parameters passed in, as well as
    executing the function
    """

    def __init__(self, function, obj, args, kwargs,
                 locking, object_type, instance_method,
                 remote_nodes,  # remote_nodes - Determine whether the remote_nodes and
                                #                return_dict arguments are used by the
                                #                wrapper to execute the method on
                                #                remote nodes, otherwise it is passed
                                #                to the function
                 support_callback):  # Determines whether the method support the _f
                                    # callback class
        """Store the original function, instance and arguments
        as member variables for the function call and undo method
        """
        # Stored list of nodes for command to be run on, if passed
        # and remove from kwargs
        if remote_nodes and 'nodes' in kwargs:
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
        self.support_callback = support_callback

        # Register instance and functions with pyro
        # @TODO This appears to never unregister,
        # which will cause memory issues as objects
        # never get destroyed.
        self.obj._register_object(self)

    def unregister(self, force=False):
        """De-register object after deletion"""
        if force or not Transaction.in_transaction():
            self.unregister_object(self)

    @property
    def _undo_function_name(self):
        """Return the name of the undo function"""
        return 'undo__%s' % self.function.__name__

    def run(self):
        """Run the function"""
        # Pause the session timeout
        self._pause_user_session()

        # If the machine is the cluster master, run
        # the fuction with the transaction abilities
        if self.obj._is_cluster_master:
            Transaction.register_function(self)

        # Catch all exceptions to ensure that user
        # session is always reset
        try:
            # If the local host is in the list of nodes
            # run the function on the local node first
            if get_hostname() in self.nodes:
                self._call_function_local()

                # Mark local node as having complete, incase
                # method doesn't do os
                self.complete()

            # Iterate over the rest of the nodes and
            # call the remote command
            for node in self.nodes:
                # Skip localhost
                if node == get_hostname():
                    continue

                # Call the remote node
                self._call_function_remote(node)

                # Mark fucntion as having complete, if not already performed
                # by method
                self.complete()

        except:
            # Also try-catch the tear-down
            try:
                # Notify that the transaction that the functino has failed
                Transaction.function_failed(self)
            except:
                # Reset user session after the command is
                # complete
                self._reset_user_session()

                # Re-raise exception
                raise

            # Reset user session after the command is
            # complete
            self._reset_user_session()

            # Print info about command execution failure
            Syslogger.logger().debug('Expose failure: %s' % str(self.nodes))

            # Re-raise exception
            raise

        # Reset user session after the command is
        # complete
        self._reset_user_session()

        # Return the data from the function
        return self._get_response_data()

    def _get_kwargs(self):
        """Obtain kwargs for passing to the function"""
        # Create copy of kwargs before modifying them
        kwargs = dict(self.nodes[self.current_node]['kwargs'])

        # Add the callback class, if supported
        if self.support_callback:
            kwargs['_f'] = self

        return kwargs

    def _call_function_local(self):
        """Perform the actual command on the local node"""
        # Set the current node to the local node
        local_hostname = get_hostname()
        self.current_node = local_hostname

        # If locking was defined, perform command with
        # log lock and call (unless performing undo)
        if self.locking:

            self.nodes[local_hostname]['return_val'] = \
                lock_log_and_call(self.function,
                                  [self.obj] + self.nodes[local_hostname]['args'],
                                  self._get_kwargs(),
                                  self.instance_method,
                                  self.object_type)

        # Otherwise run the command directly
        else:
            self.nodes[local_hostname]['return_val'] = \
                self.function(self.obj, *self.nodes[local_hostname]['args'],
                              **self._get_kwargs())

    def _call_function_remote(self, node, undo=False):
        """Run the function on a remote node"""
        # Set current node to remote node
        self.current_node = node

        # Obtain the remote object
        remote_object = self.obj.get_remote_object(node=node)

        # Determine function name, depending on whether performing
        # undo
        function_name = self.function.__name__ if not undo else self._undo_function_name

        # If undo, if the remote node doesn't have an undo method, return
        if not hasattr(remote_object, self._undo_function_name):
            return

        # Run the method by obtaining the member attribute, based on the name of
        # the callback function from of the remote object
        response = getattr(remote_object, function_name)(
            *self.nodes[node]['args'], **self._get_kwargs())

        # Store output in response
        if not undo:
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

    @Pyro4.expose
    def add_undo_argument(self, **kwargs):
        """Add an additional keyword argument to be
        passed to the undo method, when it is run
        """
        self.nodes[self.current_node]['kwargs'].update(kwargs)

    @Pyro4.expose
    def complete(self):
        """Mark the function as having completed
        successfully. Once run, if any exception occurs within
        the function (or, if in one, the rest of the transaction),
        the undo method will be called
        """
        self.nodes[self.current_node]['complete'] = True

    def undo(self):
        """Execute the undo method for the function"""
        # If the local node is in the list of complete
        # commands, then undo it first
        if (get_hostname() in self.nodes and
                self.nodes[get_hostname()]['complete'] and
                hasattr(self.obj, self._undo_function_name)):
            Syslogger.logger().debug('Undo %s %s %s %s' %
                                     (get_hostname(),
                                      self._undo_function_name,
                                      str(self.nodes[get_hostname()]['args']),
                                      str(self.nodes[get_hostname()]['kwargs'])))
            getattr(self.obj, self._undo_function_name)(
                *self.nodes[get_hostname()]['args'],
                **self.nodes[get_hostname()]['kwargs'])

        # Iterate through nodes and undo
        for node in self.nodes:
            # Skip local node
            if node == get_hostname():
                continue

            # Run the remote undo method
            Syslogger.logger().debug('Undo %s %s %s %s' %
                                     (node,
                                      self._undo_function_name,
                                      str(self.nodes[node]['args']),
                                      str(self.nodes[node]['kwargs'])))
            self._call_function_remote(node=node, undo=True)

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

    def __init__(self, locking=False, object_type=None,
                 instance_method=None, remote_nodes=False,
                 support_callback=False):
        """Setup variables passed in via decorator as member variables"""
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.remote_nodes = remote_nodes
        self.support_callback = support_callback

    def __call__(self, callback):
        """Run when object is created. The returned value is the method that is executed"""
        def inner(self_obj, *args, **kwargs):
            """Run when the wrapping method is called"""
            # Create function object and run
            function = Function(function=callback, obj=self_obj,
                                args=args, kwargs=kwargs,
                                locking=self.locking,
                                object_type=self.object_type,
                                instance_method=self.instance_method,
                                remote_nodes=self.remote_nodes,
                                support_callback=self.support_callback)
            return_val = function.run()
            function.unregister()
            return return_val

        # Expose the function
        return Pyro4.expose(inner)

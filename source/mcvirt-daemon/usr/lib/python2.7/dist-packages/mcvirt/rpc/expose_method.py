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

    # LIFO Stack of running transactions
    transactions = []

    # Determine if currently undo-ing
    undo_state = False

    @classmethod
    def in_transaction(cls):
        """Determine if a transaction is currently in progress."""
        return len(cls.transactions) > 0

    @property
    def id(self):
        """Return the ID of the transaction."""
        return self._id

    def __init__(self):
        """Setup member variables and register transaction."""
        # Determine transaction ID.
        self._id = len(Transaction.transactions)

        # Initialise LIFO stack of functions
        self.functions = []

        # Initialise with an incomplete state
        self.complete = False

        # Only register transacstion is not in an undo-state
        if not Transaction.undo_state:
            # Add the transaction to the static list of transactions
            Transaction.transactions.insert(0, self)
            Syslogger.logger().debug('Starting new transaction')

    def finish(self):
        """Mark the transaction as having been completed."""
        self.comlpete = True
        # Only remove transaction if it is the last
        # transaction in the stack
        if self.id == Transaction.transactions[-1].id:
            Syslogger.logger().debug('End of transaction stack')

            # Tear down all transactions
            for transaction in Transaction.transactions:
                # Delete each of the function objects
                for func in transaction.functions:
                    transaction.functions.remove(func)
                    func.unregister(force=True)
                    del func

            # Reset list of transactions
            Transaction.transactions = []
        else:
            # Otherwise, remove this transaction
            Syslogger.logger().debug('End of transaction')

            # Delete each of the function objects
            for func in self.functions:
                self.functions.remove(func)
                func.unregister(force=True)
                del func

            # @TODO HOW CAN THIS NO LONGER BE IN THE LIST?
            if self in Transaction.transactions:
                Transaction.transactions.remove(self)

    @classmethod
    def register_function(cls, function):
        """Register a function with the current transactions."""
        # Only register function if a transaction is in progress
        if cls.in_transaction() and not Transaction.undo_state:
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
        # If already undoing transaction, do not undo the undo methods
        if Transaction.undo_state:
            return

        Transaction.undo_state = True
        try:
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
                    transaction_ar.finish()
            else:
                # Otherwise, undo single function
                function.undo()
        except Exception, exc:
            Syslogger.logger().error('Failed during undo: %s' % str(exc))

            # If exception is thrown, remove any remaining
            # transactions and reset undo_state
            for transaction_ar in cls.transactions:
                # Mark the transaction as complete, removing
                # it from global list and all functions
                transaction_ar.finish()

            # Reset undo state flag
            Transaction.undo_state = False

            # Re-raise exception in undo
            raise
        # Reset undo state flag
        Transaction.undo_state = False


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
                 support_callback,  # Determines whether the method support the _f
                                    # callback class
                 undo_method,  # Override the name of the undo method
                 remote_method,   # Override the name of the method that is run on
                                  # remote nodes
                 remote_undo_method):  # Override the undo method for remote nodes
        """Store the original function, instance and arguments
        as member variables for the function call and undo method
        """
        # Stored list of nodes for command to be run on, if passed
        # and remove from kwargs
        if remote_nodes and 'nodes' in kwargs:
            nodes = kwargs['nodes']
            del kwargs['nodes']

        # If all nodes has been specified, then obtain them
        # from cluster
        elif remote_nodes and 'all_nodes' in kwargs:
            all_nodes = kwargs['all_nodes']
            del kwargs['all_nodes']
            if all_nodes:
                nodes = self.po__get_registered_object('cluster').get_nodes(
                    include_local=True)
            else:
                nodes = [get_hostname()]

        # Otherwise, just add the local node
        else:
            nodes = [get_hostname()]

        # If get_remote_object_kwargs was passed to function call
        # extract to use for get_remote_object call.
        # Optional dict of kwargs to pass to
        # get_remote_object method, whilst running
        # on a remote node
        if 'get_remote_object_kwargs' in kwargs:
            self.get_remote_object_kwargs = kwargs['get_remote_object_kwargs']
            del kwargs['get_remote_object_kwargs']
        else:
            self.get_remote_object_kwargs = {}

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
        self.undo_method = undo_method
        self.function = function
        self.obj = obj
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.is_complete = False
        self.support_callback = support_callback
        self.remote_method = remote_method
        self.remote_undo_method = remote_undo_method

    @property
    def convert_to_remote_object_in_args(self):
        """This object is registered with daemon in init and all required
        methods are exposed and does not have a get_remote_object method.
        As such, mark as not to be converted to a remote object when
        passed in an argument.
        """
        return False

    def unregister(self, force=False):
        """De-register object after deletion."""
        if force or not Transaction.in_transaction():
            self.unregister_object(self, debug=False)

    @property
    def _undo_function_name(self):
        """Return the name of the undo function."""
        # If running on a remote node and a remote undo method
        # is defined, return that
        if self.current_node != get_hostname() and self.remote_undo_method:
            return self.remote_undo_method

        # Otherwise, if a custom undo method is defined (for all nodes)
        # return that
        if self.undo_method:
            return self.undo_method

        # Otherwise, return default undo name for method
        return 'undo__%s' % self.function.__name__

    def run(self):
        """Run the function."""
        # Register instance and functions with pyro
        self.obj.po__register_object(self, debug=False)

        # Pause the session timeout
        self._pause_user_session()

        # If the machine is the cluster master, run
        # the fuction with the transaction abilities
        if self.obj.po__is_cluster_master:
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

        except Exception:
            # Also try-catch the tear-down
            try:
                if self.obj.po__is_cluster_master:
                    # Notify that the transaction that the functino has failed
                    Transaction.function_failed(self)
            except Exception:
                # Reset user session after the command is
                # complete
                self._reset_user_session()

                # Re-raise exception
                raise

            # Reset user session after the command is
            # complete
            self._reset_user_session()

            # Print info about command execution failure
            Syslogger.logger().error('Expose failure: %s' % str(self.nodes))
            Syslogger.logger().error("".join(Pyro4.util.getPyroTraceback()))

            # Re-raise exception
            raise

        # Reset user session after the command is
        # complete
        self._reset_user_session()

        # Return the data from the function
        return self._get_response_data()

    def _get_kwargs(self):
        """Obtain kwargs for passing to the function."""
        # Create copy of kwargs before modifying them
        kwargs = dict(self.nodes[self.current_node]['kwargs'])

        # Add the callback class, if supported
        if self.support_callback:
            kwargs['_f'] = self

        return kwargs

    def _call_function_local(self):
        """Perform the actual command on the local node."""
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
        """Run the function on a remote node."""
        # Set current node to remote node
        self.current_node = node

        # Obtain the remote object
        remote_object = self.obj.get_remote_object(node=node, **self.get_remote_object_kwargs)

        # Determine function name, depending on whether performing
        # undo
        if undo:
            function_name = self._undo_function_name
        elif self.remote_method:
            function_name = self.remote_method
        else:
            function_name = self.function.__name__

        # If undo, if the remote node doesn't have an undo method, return
        if undo and not hasattr(remote_object, self._undo_function_name):
            return

        # Convert local object in args and kwargs
        args, kwargs = self._convert_local_object(node,
                                                  self.nodes[node]['args'],
                                                  self._get_kwargs())

        # Run the method by obtaining the member attribute, based on the name of
        # the callback function from of the remote object
        response = getattr(remote_object, function_name)(
            *args, **kwargs)

        # Store output in response
        if not undo:
            self.nodes[node]['return_val'] = response

    @staticmethod
    def _convert_local_object(node, args, kwargs):
        """Convert any local objects in args and kwargs to remote objects."""
        # @TODO: Inspect lists and dicts within each argumnet
        # Create new list of args and kwargs
        args = list(args)
        kwargs = dict(kwargs)
        for itx, arg in enumerate(args):
            if (isinstance(arg, PyroObject) and
                    arg.convert_to_remote_object_in_args):
                remote_object = arg.get_remote_object(node=node)
                args[itx] = remote_object

        for key, val in kwargs.iteritems():
            if (isinstance(val, PyroObject) and
                    val.convert_to_remote_object_in_args):
                remote_object = val.get_remote_object(node=node)
                kwargs[key] = remote_object

        return args, kwargs

    def _get_response_data(self):
        """Determine and return response data."""
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
        """Add an additional keyword argument.

        This is to be passed to the undo method, when it is run.
        """
        self.nodes[self.current_node]['kwargs'].update(kwargs)

    def complete(self):
        """Mark the function as having completed successfully.

        Once run, if any exception occurs within
        the function (or, if in one, the rest of the transaction),
        the undo method will be called
        """
        self.nodes[self.current_node]['complete'] = True

    def undo(self):
        """Execute the undo method for the function."""
        # If the local node is in the list of complete
        # commands, then undo it first
        if (get_hostname() in self.nodes and
                self.nodes[get_hostname()]['complete'] and
                hasattr(self.obj, self._undo_function_name)):

            # Set current node
            local_hostname = get_hostname()
            self.current_node = local_hostname

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
            # Skip local node or if the function did not complete on the node
            if node == get_hostname() or not self.nodes[node]['complete']:
                continue

            # Run the remote undo method
            Syslogger.logger().debug('Undo %s %s %s %s' %
                                     (node,
                                      self.function.__name__,
                                      str(self.nodes[node]['args']),
                                      str(self.nodes[node]['kwargs'])))
            self._call_function_remote(node=node, undo=True)

    def _pause_user_session(self):
        """Pause the user session."""
        # Determine if session ID is present in current context and the session
        # object has
        # been set
        if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT.get_session_id():
            # Disable the expiration whilst the method runs
            Expose.SESSION_OBJECT.USER_SESSIONS[
                Expose.SESSION_OBJECT.get_session_id()
            ].disable()

    def _reset_user_session(self):
        """Reset the user session."""
        # Determine if session ID is present in current context and the
        # session object has
        # been set
        if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT.get_session_id():
            # Renew session expiry
            Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT.get_session_id()].renew()


class Expose(object):
    """Decorator for exposing method via Pyro and optional log and locking."""
    # @TODO Add permission checking, which is only performed during
    #       pyro call to method

    # Set in rpc_daemon during startup
    SESSION_OBJECT = None

    def __init__(self, locking=False, object_type=None,
                 instance_method=None, remote_nodes=False,
                 support_callback=False,
                 undo_method=None,
                 expose=True,  # Determine whether the method is actually
                               # exposed to pyro
                 remote_method=None,
                 remote_undo_method=None):
        """Setup variables passed in via decorator as member variables."""
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method
        self.remote_nodes = remote_nodes
        self.support_callback = support_callback
        self.undo_method = undo_method
        self.expose = expose
        self.remote_method = remote_method
        self.remote_undo_method = remote_undo_method

    def __call__(self, callback):
        """Run when object is created.

        The returned value is the method that is executed
        """
        def inner(self_obj, *args, **kwargs):
            """Run when the wrapping method is called."""
            # Create function object and run
            function = Function(function=callback, obj=self_obj,
                                args=args, kwargs=kwargs,
                                locking=self.locking,
                                object_type=self.object_type,
                                instance_method=self.instance_method,
                                remote_nodes=self.remote_nodes,
                                support_callback=self.support_callback,
                                undo_method=self.undo_method,
                                remote_method=self.remote_method,
                                remote_undo_method=self.remote_undo_method)
            return_val = function.run()
            function.unregister()
            return return_val

        # Expose the function
        if self.expose:
            return Pyro4.expose(inner)
        else:
            return inner

"""Provide Transaction and related classes."""

# Copyright (c) 2018 - I.T. Dev Ltd
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

    def __init__(self, function, obj, args, kwargs):
        """Store the original function, instance and arguments
        as member variables for the function call and undo method
        """
        self.function = function
        self.obj = obj
        self.args = args
        self.kwargs = kwargs
        self.is_complete = False

    def run(self):
        """Run the function"""
        # If the machine is the cluster master, run
        # the fuction with the transaction abilities
        if self.obj._is_cluster_master:
            return self._register_and_call()

        # Otherwise, run the function normally,
        # as only the cluster master deals with
        # transactions
        else:
            return self._call_function()

    def _register_and_call(self):
        """Run the function, catching any exceptions
        and calling the roll back
        """
        # Register commnad with transaction
        Transaction.register_function(self)

        try:
            # Run function
            self._call_function()

        # Catch all exceptions
        except:
            # Notify that the transaction that the functino has failed
            Transaction.function_failed(self)

            # Re-throw the error
            raise

    def _call_function(self):
        """Perform the actual command"""
        return self.function(self.obj, _f=self, *self.args, **self.kwargs)

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


class DoUndo(object):
    """Experimental decorator to perform reversal
    functions after an exception
    """

    def __call__(self, callback):
        """Overriding method, which handles undo"""
        def inner(self_obj, *args, **kwargs):
            """Run when the actual wrapping method is called"""
            # Create function object and run
            function = Function(callback, self_obj, args, kwargs)
            return function.run()

        return inner

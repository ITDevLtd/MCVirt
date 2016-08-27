"""Argument validators."""

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

import re
from mcvirt.exceptions import MCVirtTypeError


class ArgumentValidator(object):
    """Provide methods to validate argument values"""

    @staticmethod
    def validate_hostname(hostname):
        """Validate a hostname"""
        exception_message = ('Hostname must only use alpha-numeric characters and dashes,'
                             ' be 64 characters or less in length'
                             ' and start with an alpha-numeric character')

        try:
            # Check length
            if len(hostname) > 64 or not len(hostname):
                raise MCVirtTypeError(exception_message)

            disallowed = re.compile(r"[^A-Z\d-]", re.IGNORECASE)
            if disallowed.search(hostname):
                raise MCVirtTypeError(exception_message)

            if hostname.startswith('-') or hostname.endswith('-'):
                raise MCVirtTypeError(exception_message)
        except (ValueError, TypeError):
            raise MCVirtTypeError(exception_message)

    @staticmethod
    def validate_network_name(name):
        """Validate the name of a network"""
        exception_message = ('Network name must only use alpha-numeric characters and'
                             ' not be any longer than 64 characters in length')
        try:
            if len(name) > 64 or not len(name):
                raise MCVirtTypeError(exception_message)
            disallowed = re.compile(r"[^A-Z\d]", re.IGNORECASE)
            if disallowed.search(name):
                raise MCVirtTypeError(exception_message)
        except (ValueError, TypeError):
            raise MCVirtTypeError(exception_message)

    @staticmethod
    def validate_integer(value):
        """Validate integer"""
        try:
            if str(int(value)) != str(value):
                raise MCVirtTypeError('Must be an integer')
        except (ValueError, TypeError):
            raise MCVirtTypeError('Must be an integer')

    @staticmethod
    def validate_positive_integer(value):
        """Validate that a given variable is a
        positive integer
        """
        ArgumentValidator.validate_integer(value)

        if int(value) < 1:
            raise MCVirtTypeError('Not a positive integer')

    @staticmethod
    def validate_boolean(variable):
        """Ensure variable is a boolean"""
        if type(variable) is not bool:
            raise MCVirtTypeError('Not an boolean')

    @staticmethod
    def validate_drbd_resource(variable):
        """Validate DRBD resource name"""
        valid_name = re.compile('^mcvirt_vm-(.+)-disk-(\d+)$')
        result = valid_name.match(variable)
        if not result:
            raise MCVirtTypeError('Not a valid resource name')

        # Validate the hostname in the DRBD resource
        ArgumentValidator.validate_hostname(result.groups()[0])
        ArgumentValidator.validate_positive_integer(result.groups()[1])
        if int(result.groups()[1]) > 99:
            raise MCVirtTypeError('Not a valid resource name')

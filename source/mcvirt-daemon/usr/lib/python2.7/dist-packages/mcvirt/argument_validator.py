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
from mcvirt.exceptions import MCVirtTypeError, InvalidPermissionError
from mcvirt.constants import (DEFAULT_LIBVIRT_NETWORK_NAME,
                              DEFAULT_STORAGE_NAME)
from mcvirt.auth.permissions import PERMISSIONS


class ArgumentValidator(object):
    """Provide methods to validate argument values."""

    @staticmethod
    def validate_id(id_, ref_obj):
        """Verify that an ID is a valid format."""
        id_parts = id_.split('-')

        # Ensure that all parts of the ID are the correct length
        if (len(id_parts) != 3 or
                id_parts[0] != ref_obj.get_id_code() or
                len(id_parts[1]) != ref_obj.get_id_name_checksum_length() or
                len(id_parts[2]) != ref_obj.get_id_date_checksum_length()):
            raise MCVirtTypeError('Invalid Id')

        # Ensure that ID only contains alphanumeric characters
        disallowed = re.compile(r"[^A-Z\d]", re.IGNORECASE)
        if disallowed.search(id_parts[1]) or disallowed.search(id_parts[2]):
            raise MCVirtTypeError('Invalid Id')

    @staticmethod
    def validate_hostname(hostname):
        """Validate a hostname."""
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
        """Validate the name of a network."""
        exception_message = ('Network name must only use alpha-numeric characters and dashes,'
                             ' be 64 characters or less in length'
                             ' and start with an alpha-numeric character')

        if name == DEFAULT_LIBVIRT_NETWORK_NAME:
            raise MCVirtTypeError('Network name cannot be \'%s\'' % DEFAULT_LIBVIRT_NETWORK_NAME)
        try:
            if len(name) > 64 or not len(name):
                raise MCVirtTypeError(exception_message)
            disallowed = re.compile(r"[^A-Z\d-]", re.IGNORECASE)
            if disallowed.search(name):
                raise MCVirtTypeError(exception_message)
            if name.startswith('-') or name.endswith('-'):
                raise MCVirtTypeError(exception_message)
        except (ValueError, TypeError):
            raise MCVirtTypeError(exception_message)

    @staticmethod
    def validate_storage_name(name):
        """Validate the name of a storage backend."""
        exception_message = ('Storage name must only use alpha-numeric characters and dashes,'
                             ' be 64 characters or less in length'
                             ' and start with an alpha-numeric character')

        if name == DEFAULT_STORAGE_NAME:
            raise MCVirtTypeError('Storage name cannot be \'%s\'' % DEFAULT_STORAGE_NAME)
        try:
            if len(name) > 64 or not len(name):
                raise MCVirtTypeError(exception_message)
            disallowed = re.compile(r"[^A-Z\d-]", re.IGNORECASE)
            if disallowed.search(name):
                raise MCVirtTypeError(exception_message)
            if name.startswith('-') or name.endswith('-'):
                raise MCVirtTypeError(exception_message)
        except (ValueError, TypeError):
            raise MCVirtTypeError(exception_message)

    @staticmethod
    def validate_integer(value):
        """Validate integer."""
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
        """Ensure variable is a boolean."""
        if type(variable) is not bool:
            raise MCVirtTypeError('Not a boolean')

    @staticmethod
    def validate_drbd_resource(variable):
        """Validate DRBD resource name."""
        valid_name = re.compile('^mcvirt_vm-(.+)-disk-(\d+)$')
        result = valid_name.match(variable)
        if not result:
            raise MCVirtTypeError('Not a valid resource name')

        # Validate the hostname in the DRBD resource
        ArgumentValidator.validate_hostname(result.groups()[0])
        ArgumentValidator.validate_positive_integer(result.groups()[1])
        if int(result.groups()[1]) > 99:
            raise MCVirtTypeError('Not a valid resource name')

    @staticmethod
    def validate_ip_address(ip_address):
        """Validate an IPv4 IP address."""
        pattern = re.compile(r"^((([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])[ (\[]?(\.|dot)"
                             "[ )\]]?){3}([01]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5]))$")
        if not pattern.match(ip_address):
            raise MCVirtTypeError('%s is not a valid IP address' % ip_address)

    @staticmethod
    def validate_vg_name(vg_name):
        """Validate a volume group name."""
        pattern = re.compile("^[A-Z0-9a-z_-]+$")
        if not pattern.match(vg_name):
            raise MCVirtTypeError('%s is not a valid volume group name' % vg_name)

    @staticmethod
    def validate_logical_volume_name(lv_name):
        """Validate a volume group name."""
        pattern = re.compile("^[A-Z0-9a-z_-]+$")
        if not pattern.match(lv_name):
            raise MCVirtTypeError('%s is not a valid logical volume name' % lv_name)

    @staticmethod
    def validate_directory(directory):
        """Validate directory path."""
        if not re.compile("^(/)?([^/\0]+(/)?)+$").match(directory):
            raise MCVirtTypeError('%s is not a valid directory' % directory)

    @staticmethod
    def validate_file_name(file_name):
        """Validate a fileename."""
        if not re.compile("^[^/\0]+$").match(file_name):
            raise MCVirtTypeError('%s is not a valid filename' % file_name)

    @staticmethod
    def validate_group_name(group_name):
        """Validate a group name."""
        exception_message = ('Group name must only use alpha-numeric characters and dashes,'
                             ' be 64 characters or less in length'
                             ' and start with an alpha-numeric character')

        try:
            if len(group_name) > 64 or not len(group_name):
                raise MCVirtTypeError(exception_message)
            disallowed = re.compile(r"[^A-Z\d-]", re.IGNORECASE)
            if disallowed.search(group_name):
                raise MCVirtTypeError(exception_message)
            if group_name.startswith('-') or group_name.endswith('-'):
                raise MCVirtTypeError(exception_message)
        except (ValueError, TypeError):
            raise MCVirtTypeError(exception_message)

    @staticmethod
    def validate_permission(permission):
        """Ensure that a permission is valid."""
        try:
            PERMISSIONS[permission]
        except KeyError:
            raise InvalidPermissionError('Permission is not valid')

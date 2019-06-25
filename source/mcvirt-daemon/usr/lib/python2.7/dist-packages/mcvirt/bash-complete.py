#!/usr/bin/python
# Copyright (c) 2015 - I.T. Dev Ltd
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

# Script to allow bash completion, which will not be run using sudo

import argcomplete

from mcvirt.parser import Parser
from mcvirt.auth.auth import Auth


class NonSuperuserAuth(Auth):
    """Class to override the auth module, so that
       the argparser can attempt to check
       user permissions when performing bash
       completion without root privileges."""

    def __init__(self, *args, **kwargs):
        """Override inherited init function to stop
           root privilege check."""
        pass

    def check_permission(self, *args, **kwargs):
        """Return all permissions as false as they
           cannot be determined without running as root."""
        return False


if __name__ == "__main__":

    # Create auth and argparser object
    auth_object = NonSuperuserAuth()
    parser_object = Parser(auth_object=auth_object)
    argcomplete.autocomplete(parser_object.parser)

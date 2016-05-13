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

import os
from binascii import hexlify
import Pyro4

from mcvirt.exceptions import AuthenticationError, CurrentUserError
from factory import Factory as UserFactory


class Session(object):
    """Handle daemon user sessions"""

    USER_SESSIONS = {}

    def __init__(self, mcvirt_instance):
        """Create instance and store MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    def authenticateUser(self, username, password):
        """Authenticate using username/password and store
          session"""
        user_factory = UserFactory(self.mcvirt_instance)
        user_object = user_factory.authenticate(username, password)
        if user_object:
            # Generate Session ID
            session_id = Session._generateSessionId()

            # Store session ID and return
            Session.USER_SESSIONS[session_id] = username

            # Return session ID
            return session_id

        raise AuthenticationError('Invalid credentials')

    @staticmethod
    def _generateSessionId():
        """Generate random session ID"""
        return hexlify(os.urandom(8))

    def authenticateSession(self, username, session):
        """Authenticate user session"""
        if session in Session.USER_SESSIONS and Session.USER_SESSIONS[session] == username:
            user_factory = UserFactory(self.mcvirt_instance)
            return user_factory.get_user_by_username(username)

        raise AuthenticationError('Invalid session ID')

    def getCurrentUserObject(self):
        """Returns the current user object, based on pyro session"""
        if Pyro4.current_context.session_id:
            session_id = Pyro4.current_context.session_id
            username = Session.USER_SESSIONS[session_id]
            user_factory = UserFactory(self.mcvirt_instance)
            return user_factory.get_user_by_username(username)
        raise CurrentUserError('Cannot obtain current user')

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

from mcvirt.mcvirt import MCVirtException
from user import User


class AuthenticationError(MCVirtException):
    """Incorrect credentials"""
    pass


class CurrentUserError(MCVirtException):
    pass


class Session(object):

    USER_SESSIONS = {}

    @staticmethod
    def authenticateUser(username, password):
        user_object = User.authenticate(username, password)
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
        return hexlify(os.urandom(8))

    @staticmethod
    def authenticateSession(username, session):
        if session in Session.USER_SESSIONS and Session.USER_SESSIONS[session] == username:
            return User(username)

        raise AuthenticationError('Invalid session ID')

    @staticmethod
    def getCurrentUser():
        if Pyro4.current_context.session_id:
            session_id = Pyro4.current_context.session_id
            username = Session.USER_SESSIONS[session_id]
            return User(username)
        raise CurrentUserError('Cannot obtain current user')

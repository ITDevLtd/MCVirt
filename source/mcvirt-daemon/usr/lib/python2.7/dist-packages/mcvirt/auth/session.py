"""Provide class for managing authentication sessions."""

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
import time

from mcvirt.exceptions import (AuthenticationError, CurrentUserError,
                               UserDoesNotExistException)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.config.core import Core as MCVirtConfig
from mcvirt.syslogger import Syslogger


class SessionInfo(object):
    """Store information about a session."""

    def __init__(self, username, user_class):
        """Set member variables and expiry time if applicable."""
        self.username = username

        # If the user session expires, set disabled
        # to False and renew the session
        if user_class.EXPIRE_SESSION:
            self.disabled = False
            self.renew()

        # Otherwise, set disabled as True, so
        # that it never renews and expires
        # to False so that it' always valid
        else:
            self.disabled = True
            self.expires = False

    def is_valid(self):
        """Return True if this session is valid."""
        # Session is valid if expiry time is greater than
        # the current time or expires has been disabled
        return self.expires is False or self.expires > time.time()

    def renew(self):
        """Renew this session by increasing the expiry time (if applicable)"""
        # Reset the expiry time to current time + the default timeout duration
        # only if the session timeout is not disabled
        self.expires = False if self.disabled else time.time() + SessionInfo.get_timeout()

    def disable(self):
        """Disable session expiry complete. The session
        cannot be re-enabled and will never expire
        """
        self.expires = False

    @staticmethod
    def get_timeout():
        """Return the session timeout in seconds."""
        return MCVirtConfig().get_config()['session_timeout'] * 60


class Session(PyroObject):
    """Handle daemon user sessions."""

    USER_SESSIONS = {}

    @Expose()
    def dummy(self):
        """Dummy method to allow object to pyro connections"""
        pass

    def authenticate_user(self, username, password):
        """Authenticate using username/password and store
        session
        """
        user_factory = self.po__get_registered_object('user_factory')
        user_object = user_factory.authenticate(username, password)
        if user_object:
            # Generate Session ID
            session_id = Session._generate_session_id()

            # Store session ID and return
            Session.USER_SESSIONS[session_id] = SessionInfo(username, user_object.__class__)

            # Return session ID
            return session_id

        raise AuthenticationError('Invalid credentials')

    @staticmethod
    def _generate_session_id():
        """Generate random session ID."""
        return hexlify(os.urandom(8))

    def authenticate_session(self, username, session):
        """Authenticate user session."""
        Syslogger.logger().debug("Authenticating session for user %s: %s" % (username, session))

        if (session in Session.USER_SESSIONS and
                Session.USER_SESSIONS[session].username == username):

            # Check session has not expired
            if Session.USER_SESSIONS[session].is_valid():
                Session.USER_SESSIONS[session].renew()
                user_factory = self.po__get_registered_object('user_factory')
                return user_factory.get_user_by_username(username)
            else:
                del Session.USER_SESSIONS[session]

        raise AuthenticationError('Invalid session ID')

    def get_proxy_user_object(self):
        """Return the user that is being proxied as."""
        current_user = self.get_current_user_object()
        user_factory = self.po__get_registered_object('user_factory')
        if (current_user.allow_proxy_user and 'proxy_user' in dir(Pyro4.current_context) and
                Pyro4.current_context.proxy_user):
            try:
                return user_factory.get_user_by_username(Pyro4.current_context.proxy_user)
            except UserDoesNotExistException:
                pass
        return current_user

    def get_current_user_object(self):
        """Return the current user object, based on pyro session."""
        if Pyro4.current_context.session_id:
            session_id = Pyro4.current_context.session_id
            username = Session.USER_SESSIONS[session_id].username
            user_factory = self.po__get_registered_object('user_factory')
            return user_factory.get_user_by_username(username)
        raise CurrentUserError('Cannot obtain current user')

    # @Expose()
    # def get_session_id(self):
    #     """Return the client's current session ID."""
    #     return self.get_session_id()

    def get_session_id(self):
        """Return the client's current session ID."""
        if 'session_id' in dir(Pyro4.current_context) and Pyro4.current_context.session_id:
            return Pyro4.current_context.session_id

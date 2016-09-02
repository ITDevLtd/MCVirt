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


class Expose(object):

    SESSION_OBJECT = None

    def __init__(self, locking=False, object_type=None, instance_method=None):
        self.locking = locking
        self.object_type = object_type
        self.instance_method = instance_method

    def __call__(self, callback):
        def inner(*args, **kwargs):
            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Renew session expiry
                Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].disable()
            # TODO: lock if locking is True
            if self.locking:
                return_value = lock_log_and_call(callback, args, kwargs, self.instance_method,
                                                 self.object_type)
            else:
                return_value = callback(*args, **kwargs)

            # Determine if session ID is present in current context and the session object has
            # been set
            if Expose.SESSION_OBJECT is not None and Expose.SESSION_OBJECT._get_session_id():
                # Renew session expiry
                Expose.SESSION_OBJECT.USER_SESSIONS[Expose.SESSION_OBJECT._get_session_id()].renew()

            return return_value
        # Expose the function
        return Pyro4.expose(inner)
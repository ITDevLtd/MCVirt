"""Provide class for regular MCVirt interactive users"""

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

from mcvirt.auth.user_base import UserBase
from mcvirt.exceptions import OldPasswordIncorrect


class User(UserBase):
    """Provides an interaction with the local user backend"""

    def change_password(self, old_password, new_password):
        """Change the current user's password."""
        if not self._check_password(old_password):
            raise OldPasswordIncorrect('Old password is not correct')
        self._set_password(new_password)

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

from psutil import cpu_percent, virtual_memory


class OSStats(object):
    """Provide functions to obtain VM functions."""

    @staticmethod
    def get_cpu_usage():
        """Obtain CPU usage statistics."""
        return cpu_percent()

    @staticmethod
    def get_ram_usage():
        """Get memory usage statistics."""
        return virtual_memory().percent

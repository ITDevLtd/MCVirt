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

import socket


def get_hostname():
    """Return the hostname of the system"""
    return socket.gethostname()


def get_all_submodules(target_class):
    """Return all inheriting classes, recursively"""
    subclasses = []
    for subclass in target_class.__subclasses__():
        subclasses.append(subclass)
        subclasses += get_all_submodules(subclass)
    return subclasses


def convert_size_friendly(original):
    """Convert from MB to a readable size, depneding on
    size
    """

    if original <= 1024:
        return '%iMB' % original
    elif original < (1024 ** 2):
        return '%.2fGB' % round(float(original) / 1024, 2)
    else:
        return '%.2fTB' % round(float(original) / (1024 ** 2), 2)

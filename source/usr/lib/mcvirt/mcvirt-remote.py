#!/usr/bin/python
# Copyright (c) 2014 - I.T. Dev Ltd
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

import sys

sys.path.insert(0, '/usr/lib')

from mcvirt.mcvirt import MCVirt
from cluster.remote import Remote

mcvirt_instance = MCVirt(None, initialise_nodes=False)

end_conection = False
try:
    while True:
        data = str.strip(sys.stdin.readline())
        (output, end_conection) = Remote.receiveRemoteCommand(mcvirt_instance, data)

        sys.stdout.write("%s\n" % output)
        sys.stdout.flush()

        if (end_conection):
            break
except Exception as e:
    mcvirt_instance = None
    raise Exception, e, sys.exc_info()[2]

mcvirt_instance = None

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

from mcvirt.thread.repeat_timer import RepeatTimer
from mcvirt.constants import AutoStartStates


class AutoStartWatchdog(RepeatTimer):

    @property
    def interval(self):
        return self._get_registered_object('mcvirt_config')().get_config()['autostart_interval']

    def initialise(self):
        Pyro4.current_context.INTERNAL_REQUEST = True
        vm_factory = self._get_registered_object('virtual_machine_factory')
        vm_factory.autostart(AutoStartStates.ON_BOOT)
        Pyro4.current_context.INTERNAL_REQUEST = False
        super(AutoStartWatchdog, self).initialise()

    def run(self):
        Pyro4.current_context.INTERNAL_REQUEST = True
        vm_factory = self._get_registered_object('virtual_machine_factory')
        vm_factory.autostart(AutoStartStates.ON_POLL)
        Pyro4.current_context.INTERNAL_REQUEST = False

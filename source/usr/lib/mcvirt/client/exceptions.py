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
from mcvirt.mcvirt import MCVirtException, ConnectionFailureToRemoteLibvirtInstance
from mcvirt.virtual_machine.virtual_machine import (UnkownException, InvalidVirtualMachineNameException,
                                                    VmAlreadyStoppedException, VmAlreadyStartedException)
from mcvirt.virtual_machine.factory import StorageTypeNotSpecified
from mcvirt.virtual_machine.network_adapter import NetworkAdapterDoesNotExistException
from mcvirt.node.network.factory import NetworkAlreadyExistsException
from mcvirt.node.network.network import NetworkDoesNotExistException, NetworkUtilizedException
from mcvirt.virtual_machine.hard_drive.factory import UnknownStorageTypeException
from mcvirt.auth.auth import InsufficientPermissionsException
from mcvirt.auth.user_base import UserDoesNotExistException

for exception_class in [UnkownException, MCVirtException,
                        InvalidVirtualMachineNameException, StorageTypeNotSpecified,
                        NetworkAdapterDoesNotExistException, NetworkAlreadyExistsException,
                        NetworkDoesNotExistException, NetworkUtilizedException,
                        UnknownStorageTypeException, InsufficientPermissionsException,
                        UserDoesNotExistException, VmAlreadyStoppedException,
                        VmAlreadyStartedException]:
    Pyro4.util.all_exceptions['%s.%s' % (exception_class.__module__, exception_class.__name__)] = exception_class

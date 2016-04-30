import Pyro4
from mcvirt.mcvirt import MCVirtException, ConnectionFailureToRemoteLibvirtInstance
from mcvirt.virtual_machine.virtual_machine import UnkownException, InvalidVirtualMachineNameException
from mcvirt.virtual_machine.factory import StorageTypeNotSpecified

for exception_class in [UnkownException, MCVirtException,
                        InvalidVirtualMachineNameException, StorageTypeNotSpecified]:
    Pyro4.util.all_exceptions['%s.%s' % (exception_class.__module__, exception_class.__name__)] = exception_class

from mcvirt.mcvirt import MCVirtException, ConnectionFailureToRemoteLibvirtInstance
from mcvirt.virtual_machine.virtual_machine import UnkownException,

for exception_class in [UnkownException, MCVirtException]:
    Pyro4.util.all_exceptions['%s.%s' % (exception_class.__module__, exception_class.__name__)] = exception_class

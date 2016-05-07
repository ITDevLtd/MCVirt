import Pyro4
from mcvirt.mcvirt import MCVirtException, ConnectionFailureToRemoteLibvirtInstance
from mcvirt.virtual_machine.virtual_machine import UnkownException, InvalidVirtualMachineNameException
from mcvirt.virtual_machine.factory import StorageTypeNotSpecified
from mcvirt.virtual_machine.network_adapter import NetworkAdapterDoesNotExistException
from mcvirt.node.network.factory import NetworkAlreadyExistsException
from mcvirt.node.network.network import NetworkDoesNotExistException, NetworkUtilizedException
from mcvirt.virtual_machine.hard_drive.factory import UnknownStorageTypeException

for exception_class in [UnkownException, MCVirtException,
                        InvalidVirtualMachineNameException, StorageTypeNotSpecified,
                        NetworkAdapterDoesNotExistException, NetworkAlreadyExistsException,
                        NetworkDoesNotExistException, NetworkUtilizedException,
                        UnknownStorageTypeException]:
    Pyro4.util.all_exceptions['%s.%s' % (exception_class.__module__, exception_class.__name__)] = exception_class

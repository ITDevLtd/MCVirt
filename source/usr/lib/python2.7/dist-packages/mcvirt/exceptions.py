"""Provide access to all MCVirt exceptions."""

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

from mcvirt.utils import get_all_submodules


# Exceptions can be tagged using:
# Namespace (e.g. VirtualMachine) - Useful for a particular namepsace
# Common - Shared exceptions used throughout the codebase

class MCVirtException(Exception):
    """Provide an exception to be thrown for errors in MCVirt"""

    pass


class ConnectionFailureToRemoteLibvirtInstance(MCVirtException):
    """Connection failure whilst attempting to obtain a remote libvirt connection"""

    pass


class CACertificateNotFoundException(MCVirtException):
    """CA certificate for host could not be found"""

    pass


class OpenSSLNotFoundException(MCVirtException):
    """The OpenSSL executable could not be found"""

    pass


class UserNotPresentInGroup(MCVirtException):
    """User to be removed from group is not in the group"""

    pass


class InsufficientPermissionsException(MCVirtException):
    """User does not have the required permission"""

    pass


class UnprivilegedUserException(MCVirtException):
    """Unprivileged user running executable"""

    pass


class InvalidPermissionGroupException(MCVirtException):
    """Attempted to perform actions on an invalid permission group"""

    pass


class MCVirtLockException(MCVirtException):
    """A lock has already been found"""

    pass


class LibVirtConnectionException(MCVirtException):
    """An error occurred whilst connecting to LibVirt"""

    pass


class DuplicatePermissionException(MCVirtException):
    """User already exists in group"""

    pass


class NodeAlreadyPresent(MCVirtException):
    """Node being added is already connected to cluster"""

    pass


class NodeDoesNotExistException(MCVirtException):
    """The node does not exist. Tag: Cluster"""

    pass


class RemoteObjectConflict(MCVirtException):
    """The remote node contains an object that will cause conflict when syncing"""

    pass


class ClusterNotInitialisedException(MCVirtException):
    """The cluster has not been initialised, so cannot connect to the remote node. Tag: Cluster"""

    pass


class InvalidConnectionString(MCVirtException):
    """Connection string is invalid"""

    pass


class CAFileAlreadyExists(MCVirtException):
    """The CA file already exists."""

    pass


class IncorrectCredentials(MCVirtException):
    """The supplied credentials are incorrect. Tag: Authentication"""

    pass


class InvalidUsernameException(MCVirtException):
    """Username is within a reserved namespace. Tag: Authentication"""

    pass


class AuthenticationError(MCVirtException):
    """Incorrect credentials. Tag: Authentication"""

    pass


class CurrentUserError(MCVirtException):
    """Error whilst obtaining current pyro user. Tag: Authentication"""

    pass


class UserDoesNotExistException(MCVirtException):
    """The specified user does not exist. Tag: Authentication"""

    pass


class PasswordsDoNotMatchException(MCVirtException):
    """The new passwords do not match. Tag: Authentication"""

    pass


class RemoteCommandExecutionFailedException(MCVirtException):
    """A remote command execution fails. Tag: Cluster"""

    pass


class UnknownRemoteCommandException(MCVirtException):
    """An unknown command was passed to the remote machine. Tag: Cluster"""

    pass


class NodeAuthenticationException(MCVirtException):
    """Incorrect password supplied for remote nodeTag: Cluster"""

    pass


class CouldNotConnectToNodeException(MCVirtException):
    """Could not connect to remove cluster node. Tag: Cluster"""

    pass


class RemoteNodeLockedException(MCVirtException):
    """Remote node is locked. Tag: Cluster"""

    pass


class IsoNotPresentOnDestinationNodeException(MCVirtException):
    """ISO attached to VM does not exist on destination node
    whilst performing a migration]
    """

    pass


class InvalidISOPathException(MCVirtException):
    """ISO to add does not exist"""

    pass


class NameNotSpecifiedException(MCVirtException):
    """A name has not been specified and cannot be determined by the path/URL"""

    pass


class IsoAlreadyExistsException(MCVirtException):
    """An ISO with the same name already exists"""

    pass


class FailedToRemoveFileException(MCVirtException):
    """A failure occurred whilst trying to remove an ISO"""

    pass


class IsoInUseException(MCVirtException):
    """The ISO is in use, so cannot be removed"""

    pass


class DrbdNotInstalledException(MCVirtException):
    """Drbd is not installed. Tag: Drbd"""

    pass


class DrbdAlreadyEnabled(MCVirtException):
    """Drbd has already been enabled on this node. Tag: Drbd"""

    pass


class DrbdNotEnabledOnNode(MCVirtException):
    """Drbd volumes cannot be created on a node that
    has not been configured to use Drbd.
    Tag: Drbd
    """

    pass


class NetworkAlreadyExistsException(MCVirtException):
    """Network already exists with the same name"""

    pass


class LibvirtException(MCVirtException):
    """Issue with performing libvirt command"""

    pass


class NetworkDoesNotExistException(MCVirtException):
    """Network does not exist"""

    pass


class NetworkUtilizedException(MCVirtException):
    """Network is utilized by virtual machines"""

    pass


class ArgumentParserException(MCVirtException):
    """An invalid argument was provided. Tag: Common"""

    pass


class StorageTypeNotSpecified(MCVirtException):
    """Storage type has not been specified"""

    pass


class InvalidNodesException(MCVirtException):
    """The nodes passed is invalid. Tag: Common"""

    pass


class HardDriveDoesNotExistException(MCVirtException):
    """The given hard drive does not exist"""

    pass


class StorageTypesCannotBeMixedException(MCVirtException):
    """Storage types cannot be mixed within a single VM"""

    pass


class LogicalVolumeDoesNotExistException(MCVirtException):
    """A required logical volume does not exist"""

    pass


class LogicalVolumeIsNotActiveException(MCVirtException):
    """Logical volume is not active"""

    pass


class BackupSnapshotAlreadyExistsException(MCVirtException):
    """The backup snapshot for the logical volume already exists"""

    pass


class BackupSnapshotDoesNotExistException(MCVirtException):
    """The backup snapshot for the logical volume does not exist"""

    pass


class ExternalStorageCommandErrorException(MCVirtException):
    """An error occurred whilst performing an external command"""

    pass


class ReachedMaximumStorageDevicesException(MCVirtException):
    """Reached the limit to number of hard disks attached to VM"""

    pass


class DrbdStateException(MCVirtException):
    """The Drbd state is not OK"""

    pass


class DrbdBlockDeviceDoesNotExistException(MCVirtException):
    """Drbd block device does not exist"""

    pass


class DrbdVolumeNotInSyncException(MCVirtException):
    """The last Drbd verification of the volume failed"""

    pass


class InsufficientSpaceException(MCVirtException):
    """A hard drive object was initialised when the volume group did not have enough space."""

    pass


class UnknownStorageTypeException(MCVirtException):
    """An hard drive object with an unknown disk type has been initialised"""

    pass


class NetworkAdapterDoesNotExistException(MCVirtException):
    """The network adapter does not exist"""

    pass


class ConfigFileCouldNotBeFoundException(MCVirtException):
    """Config file could not be found"""

    pass


class MigrationFailureExcpetion(MCVirtException):
    """A Libvirt Exception occurred whilst performing a migration"""

    pass


class InvalidVirtualMachineNameException(MCVirtException):
    """VM is being created with an invalid name"""

    pass


class VmAlreadyExistsException(MCVirtException):
    """VM is being created with a duplicate name"""

    pass


class VmDirectoryAlreadyExistsException(MCVirtException):
    """Directory for a VM already exists"""

    pass


class VmAlreadyStoppedException(MCVirtException):
    """VM is already stopped when attempting to stop it"""

    pass


class VmAlreadyStartedException(MCVirtException):
    """VM is already started when attempting to start it"""

    pass


class VmAlreadyRegisteredException(MCVirtException):
    """VM is already registered on a node"""

    pass


class VmRegisteredElsewhereException(MCVirtException):
    """Attempt to perform an action on a VM registered on another node"""

    pass


class VmRunningException(MCVirtException):
    """An offline migration can only be performed on a powered off VM"""

    pass


class VmStoppedException(MCVirtException):
    """An online migration can only be performed on a powered on VM"""

    pass


class UnsuitableNodeException(MCVirtException):
    """The node is unsuitable to run the VM. Tag: Common"""

    pass


class VmNotRegistered(MCVirtException):
    """The virtual machine is not currently registered on a node"""

    pass


class CannotStartClonedVmException(MCVirtException):
    """Cloned VMs cannot be started"""

    pass


class CannotCloneDrbdBasedVmsException(MCVirtException):
    """Cannot clone Drbd-based VMs"""

    pass


class CannotDeleteClonedVmException(MCVirtException):
    """Cannot delete a cloned VM"""

    pass


class VirtualMachineLockException(MCVirtException):
    """Lock cannot be set to the current lock state"""

    pass


class InvalidArgumentException(MCVirtException):
    """
    Argument given is not valid.
    Tag: Common
    @TODO remove in favour of ArgumentParserException
    """

    pass


class VirtualMachineDoesNotExistException(MCVirtException):
    """Virtual machine does not exist"""

    pass


class VmIsCloneException(MCVirtException):
    """VM is a clone"""

    pass


class VncNotEnabledException(MCVirtException):
    """VNC is not enabled on the VM"""

    pass


class CannotMigrateLocalDiskException(MCVirtException):
    """Local disks cannot be migrated"""

    pass


class DiskAlreadyExistsException(MCVirtException):
    """The disk already exists"""

    pass


class MCVirtCommandException(MCVirtException):
    """Provides an exception to be thrown after errors whilst calling external commands"""

    pass


class InterfaceDoesNotExist(MCVirtException):
    """Physical interface does not exist"""

    pass


class MissingConfigurationException(MCVirtException):
    """Configuration is missing"""

    pass


class CACertificateAlreadyExists(MCVirtException):
    """CA file for server already exists"""

    pass


class MustGenerateCertificateException(MCVirtException):
    """The certificate cannot be manually added and must be generated"""

    pass


class InvalidUserTypeException(MCVirtException):
    """An invalid user type was specified."""

    pass


class UserAlreadyExistsException(MCVirtException):
    """The given user already exists."""

    pass


class LibvirtNotInstalledException(MCVirtException):
    """Libvirt does not appear to be installed"""

    pass


class AttributeAlreadyChanged(MCVirtException):
    """Attribute, user is trying to change, has already changed"""

    pass


class BlankPasswordException(MCVirtException):
    """The provided password is blank"""

    pass


class NodeVersionMismatch(MCVirtException, Pyro4.errors.SecurityError):
    """A node is running a different version of MCVirt. Tag: Cluster"""

    pass


class InaccessibleNodeException(MCVirtException, Pyro4.errors.SecurityError):
    """Unable to connect to node in the cluster. Tag: Cluster"""

    pass


class LdapConnectionFailedException(MCVirtException):
    """Connection to the LDAP server failed"""

    pass


class LdapNotEnabledException(MCVirtException):
    """Ldap has not been enabled on the node"""

    pass


class ResyncNotSupportedException(MCVirtException):
    """Resync is not supported on this storage type"""

    pass


class InvalidGraphicsDriverException(MCVirtException):
    """The provided graphics driver name was not valid"""

    pass


class TooManyParametersException(MCVirtException):
    """Too many parameters have been defined. Tag: Common"""

    pass


class InvalidModificationFlagException(MCVirtException):
    """The provided modification flag name was invalid"""

    pass


class MCVirtTypeError(MCVirtException):
    """TypeError raised by MCVirt. Tag: Common"""

    pass


class UsbDeviceAttachedToVirtualMachine(MCVirtException):
    """The USB device is already attached to a virtual machine"""

    pass


class UnknownLdapError(MCVirtException):
    """An unknown LDAP error has occurred"""

    pass


class StorageBackendDoesNotExist(MCVirtException):
    """Storage backend does not exist"""

    pass


class InvalidStorageConfiguration(MCVirtException):
    """Invalid storage configuration"""

    pass


class NodeAlreadyConfiguredInStorageBackend(MCVirtException):
    """Node is already configured for the storage backend"""

    pass


class StorageBackendInUse(MCVirtException):
    """Storage is in use and cannot be deleted"""

    pass


class StorageBackendNotAvailableOnNode(MCVirtException):
    """Storage backend defined, is not available on the given node"""

    pass


class UnknownStorageBackendException(MCVirtException):
    """Storage backend either not specified and multiple avialaable or
    no storage backends available
    """

    pass


class VolumeDoesNotExistError(MCVirtException):
    """Volume does not exist"""

    pass


class VolumeAlreadyExistsError(MCVirtException):
    """Volume already exists"""

    pass


for exception_class in get_all_submodules(MCVirtException):
    Pyro4.util.all_exceptions[
        '%s.%s' % (exception_class.__module__, exception_class.__name__)
    ] = exception_class

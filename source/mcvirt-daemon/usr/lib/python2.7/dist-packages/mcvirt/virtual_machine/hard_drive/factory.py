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

"""
#########################################################################################
##################################   STORAGE  LAYOUT   ##################################
#########################################################################################
#
#        ------------
#       | Hard drive | Provides an interface for libvirt
#    ---|    Base    | configuration, high level 'creation', 'deletion'
#    |   ------------  function. Handling pre/post migration tasks and
#    |        |        determining capabilities of hard drive.
#    |        |        This class does not interact with the OS to modify
#    |        |        actual storage (with the exception of DRBD commands).
#    |        |        This class performs all non-OS-level-storage checking
#    |        |        before actions are performed, e.g. ensure VM is powered
#    |        |        off and checking user permissions.
#    |        |        The object can be created before volume exists on disk.
#    |        |
#    |        |--- Local
#    |        |      - Local hard drive object provides
#    |        |        an interface for a single-volume backed storage.
#    |        |        This could be used for either be a single-node VM or
#    |        |        on shared storage
#    |        |
#    |        |
#    |        |
#    |         --- Drbd
#    |               - DRBD object provides additional overlay for managing
#    |                 the multiple backend volumes, that's required by DRBD,
#    |                 an alternative front-end block devide (drbd volume),
#    |                 as well as montioring of the DRBD volume. This must
#    |                 use local storage, as the volume is replicatated
#    |                 to other nodes via DRBD. All DRBD commands are executed
#    |                 from this class
#    |
#    |      --------
#     ---> | Volume |  Given the storage backend (as supplied by the disk object
#       -> |  Base  |  when creating the volume object), this class provides
#      |    --------   and interface to interact with the OS to create/modify
#      |       |       the underlying storage volumes. All 'create', 'delete' etc.,
#      |       |       commands in the hard drive objects call to the respective
#      |       |       volume objects to make the system modification. This object
#      |       |       has no concept of a virtual machine, it performs disks commands,
#      |       |       given the disk name and storage backend.
#      |       |       The object can be created before the volume exists on disk.
#.     |       |
#      |       |--- LVM
#      |       |       This performs OS commands to manage a given logival-volume-based
#      |       |       disk, where the underlying storage backend is LVM-based.
#      |       |
#      |        --- File
#      |               This performs OS commands to manage a given file-based disk,
#      |               where the underlying storage backend is Directory-based.
#      |
#      |     -----------
#       ----|  Storage  | Provides an interface for managing/differentiating different
#           | (Backend) | sets/types of physical storage. When this object is created,
#           |    Base   | the backing storage must be present on the requested nodes.
#            -----------  This object is used to determine which nodes the storage is
#               |         available to and contribute to which nodes a VM will be
#               |         compatible with.
#               |
#               |------- LVM
#               |      Allows for addition of LVM volume-group based storage.
#               |      When a disk object is created, using this as a storage backend,
#               |      an LVM-based volume is returned for OS-calls.
#               |
#                ------- File
#                      Allows for addition of directory based storage.
#                      When a disk object is created, using this as a storage backend,
#                      an File volume is returned for OS-calls.
#
#########################################################################################
#########################################################################################
"""

from texttable import Texttable

from mcvirt.exceptions import (UnknownStorageTypeException, HardDriveDoesNotExistException,
                               InsufficientSpaceException, StorageBackendNotAvailableOnNode,
                               UnknownStorageBackendException, InvalidNodesException,
                               InvalidStorageBackendError, VolumeDoesNotExistError,
                               HardDriveDoesNotExistException,
                               StorageBackendDoesNotExist)
from mcvirt.virtual_machine.hard_drive.local import Local
from mcvirt.virtual_machine.hard_drive.drbd import Drbd
from mcvirt.virtual_machine.hard_drive.base import Base
from mcvirt.config.hard_drive import HardDrive as HardDriveConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.utils import get_hostname, get_all_submodules
from mcvirt.rpc.expose_method import Expose, Transaction
from mcvirt.size_converter import SizeConverter


class Factory(PyroObject):
    """Provides a factory for creating hard drive/hard drive config objects."""

    DEFAULT_STORAGE_TYPE = 'Local'
    OBJECT_TYPE = 'hard disk'
    HARD_DRIVE_CLASS = Base
    CACHED_OBJECTS = {}

    @Expose()
    def get_object_by_vm_and_attachment_id(self, vm_object, attachment_id):
        """Return the disk object based on virtual machine and attachment Id."""
        return self._get_registered_object(
            'hard_drive_attachment_factory').get_object(
                vm_object, attachment_id).get_hard_drive_object()

    @Expose()
    def get_object(self, id_):
        """Returns the storage object for a given disk."""

        if id_ not in Factory.CACHED_OBJECTS:
            base_hdd = Base(id_)
            storage_type = base_hdd.get_type()
            hard_drive_object = self.getClass(storage_type)(id_)
            self._register_object(hard_drive_object)
            Factory.CACHED_OBJECTS[id_] = hard_drive_object

        return Factory.CACHED_OBJECTS[id_]

    def get_remote_object(self,
                          node=None,  # The name of the remote node to connect to
                          node_object=None):  # Otherwise, pass a remote node connection
        """Obtain an instance of the hard drive factory on a remote node."""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('hard_drive_factory')

    @Expose()
    def ensure_hdd_valid(self, size, storage_type, nodes, storage_backend, nodes_predefined=False):
        """Ensures the HDD can be created on all nodes, and returns the storage type to be used."""

        # Ensure that, if storage type is specified, that it's in the list of available storage
        # backends for this node.
        # @TODO IF a storage type has been specified, which does not support DBRD, then
        # we can assume that Local storage is used.
        available_storage_types = self._get_available_storage_types()
        if storage_type:
            if (storage_type not in
                    [available_storage.__name__ for available_storage in available_storage_types]):
                raise UnknownStorageTypeException('%s is not supported by node %s' %
                                                  (storage_type, get_hostname()))
        else:
            # Otherwise, if no storage type has been defined, ensure that there is only
            # 1 avilable storage type.
            if len(available_storage_types) > 1:
                raise UnknownStorageTypeException('Storage type must be specified')
            elif len(available_storage_types) == 1:
                storage_type = available_storage_types[0].__name__
            else:
                raise UnknownStorageTypeException('There are no storage types available')

        # Before any further calculations are performed, if DRBD has been selected
        # and there are more or fewer than 2 available nodes with DRBD enabled,
        # the user MUST determine which two nodes will be used.
        if storage_type == Drbd.__name__:
            node_drbd = self._get_registered_object('node_drbd')
            for node in nodes:
                # If DRBD is not enabled on the node, remove it from the list
                # of nodes
                if not node_drbd.is_enabled(node=node):
                    if nodes_predefined:
                        raise InvalidNodesException('DRBD is not enabled on node %s' % node)
                    else:
                        nodes.delete(node)

            # If number of nodes is less than or greater than 2, raise exceptions, as
            # DRBD requires exactly 2 nodes
            if len(nodes) != node_drbd.CLUSTER_SIZE:
                raise InvalidNodesException('Exactly %i nodes must be specified for DRBD'
                                            % node_drbd.CLUSTER_SIZE)

            # Now that it's been determined that DRBD is being used and the correct number
            # of nodes is available, then nodes_predefined will be set to True to
            # stop the nodes being changed whilst storage backend is determined
            nodes_predefined = True

        # Since DRBD was not specified/determined, if storage type has not been determined,
        # force Local storage
        elif storage_type is None:
            storage_type = Local.__name__

        # If storage backend has been defined, ensure it is available on the current node
        if storage_backend:
            storage_backend = self._convert_remote_object(storage_backend)
            # Ensure that the storage backend is suitable for the storage type
            if storage_type == Drbd.__name__ and not storage_backend.is_drbd_suitable():
                raise InvalidStorageBackendError('Storage backend does not support DRBD')

            for node in nodes:
                if nodes_predefined:
                    storage_backend.available_on_node(node=node, raise_on_err=True)
                elif not storage_backend.available_on_node(node=node, raise_on_err=False):
                    nodes.remove(node)

        # Otherwise, if storage backend has not been defined, ensure that
        # there is only one available for the given storage type and nodes selected
        else:
            # Obtain all storage backends available, given the nodes (and whether they
            # must all be required - based on nodes_predefined) and whether DRBD is required
            storage_factory = self._get_registered_object('storage_factory')
            available_storage_backends = storage_factory.get_all(
                nodes=nodes, drbd=(storage_type == Drbd.__name__),
                nodes_predefined=nodes_predefined
            )
            # Ensure that only one storage backend was found, otherwise throw an error.
            if len(available_storage_backends) > 1:
                raise UnknownStorageBackendException('Storage backend must be specified')
            elif len(available_storage_backends) == 1:
                storage_backend = available_storage_backends[0]
                if not nodes_predefined:
                    nodes = storage_backend.nodes
            else:
                raise UnknownStorageBackendException('There are no available storage backends')

        # Remove any nodes from the list of nodes that aren't
        # available to the node
        for node in nodes:
            if node not in storage_backend.nodes:
                nodes.remove(node)

        # If storage is not shared and local storage type,
        # available nodes can only be 1 node, so calculate it
        if (storage_type == Local.__name__ and
                not storage_backend.shared):
            if len(nodes) != 1:
                if nodes_predefined or get_hostname() not in nodes:
                    raise InvalidNodesException(
                        ('Non-shared local storage must be assigned to a '
                         'single node and local not is not available'))
                else:
                    nodes = [get_hostname()]

        # Ensure that there is free space on all nodes
        free_space = storage_backend.get_free_space(nodes=nodes, return_dict=True)
        for node in free_space:
            if free_space[node] < size:
                raise InsufficientSpaceException('Attempted to create a disk with %s, '
                                                 'but there is only %s of free space '
                                                 'available in storage backend \'%s\' '
                                                 'on node %s.' %
                                                 (SizeConverter(size).to_string(),
                                                  SizeConverter(free_space[node]).to_string(),
                                                  storage_backend.name,
                                                  node))

        return nodes, storage_type, storage_backend

    @Expose(locking=True, support_callback=True)
    def create(self, size, storage_type, driver, storage_backend=None,
               nodes=None, skip_create=False, vm_object=None, _f=None):
        """Performs the creation of a hard drive, using a given storage type."""
        if vm_object is not None:
            vm_object = self._convert_remote_object(vm_object)
        if storage_backend is not None:
            storage_backend = self._convert_remote_object(storage_backend)

        # Convert disk size to bytes
        size = (size
                if type(size) is int else
                SizeConverter.from_string(size, storage=True).to_bytes())

        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE,
            vm_object
        )

        # Determine nodes that the VM is already available to
        nodes_predefined = True
        if nodes is None:
            if vm_object:
                nodes = vm_object.getAvailableNodes()
            else:
                nodes = self._get_registered_object('cluster').get_nodes(include_local=True)
                nodes_predefined = False
        else:
            for node in nodes:
                self._get_registered_object('cluster').ensure_node_exists(
                    node, include_local=True)

        # Specify nodes_predefined to stop available nodes from being changed when
        # determining storage specifications
        nodes, storage_type, storage_backend = self.ensure_hdd_valid(
            size, storage_type, nodes, storage_backend,
            nodes_predefined=nodes_predefined)

        # Genrate ID for hard drive
        id_ = self.getClass(storage_type).generate_id('whatshouldthisbe')
        _f.add_undo_argument(id_=id_)

        # Generate config for hard drive
        config = self.getClass(storage_type).generate_config(
            driver=driver,
            storage_backend=storage_backend,
            nodes=nodes,
            base_volume_name='mcvirt-%s' % id_)

        t = Transaction()

        # Create the config for the hard drive on all nodes
        cluster = self._get_registered_object('cluster')
        self.create_config(
            vm_object, id_, config,
            nodes=cluster.get_nodes(include_local=True))

        # Obtain object, create actual volume
        hdd_object = self.get_object(id_)

        if not skip_create:
            hdd_object.create(size=size)

        # Attach to VM
        if vm_object:
            self._get_registered_object('hard_drive_attachment_factory').create(
                vm_object, hdd_object)

        t.finish()

        return hdd_object

    def undo__create(self, size, storage_type, driver, storage_backend=None,
                     nodes=None, skip_create=False, vm_object=None, id_=None,
                     _p=None):
        """Undo create of the drive."""
        hard_drive_object = self.get_object(id_)
        hard_drive_object.delete()

    @Expose(locking=True)
    def import_(self, base_volume_name, storage_backend, node=None,
                driver=None, virtual_machine=None):
        """Import a local disk."""
        if virtual_machine:
            virtual_machine = self._convert_remote_object(virtual_machine)
        storage_backend = self._convert_remote_object(storage_backend)

        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE,
            virtual_machine
        )

        if node is None:
            node = get_hostname()

        storage_type = 'Local'
        id_ = self.getClass(storage_type).generate_id('whatshouldthisbe')
        config = self.getClass(storage_type).generate_config(
            driver=driver,
            storage_backend=storage_backend,
            nodes=[node],
            base_volume_name=base_volume_name)

        t = Transaction()

        self.create_config(
            virtual_machine, id_, config,
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

        hdd_object = self.get_object(id_)
        hdd_object.ensure_exists()

        # Attach to VM
        if virtual_machine:
            self._get_registered_object('hard_drive_attachment_factory').create(
                virtual_machine, hdd_object)

        t.finish()

        return hdd_object

    @Expose(locking=True, remote_nodes=True)
    def create_config(self, vm_object, id_, config):
        """Create the hard drive config."""
        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE,
            vm_object
        )
        HardDriveConfig.create(id_, config)

    @Expose(locking=True)
    def undo__create_config(self, vm_object, id_, config):
        """Undo creating VM object."""
        # Ensure that the user has permissions to add create storage
        self._get_registered_object('auth').assert_permission(
            PERMISSIONS.MODIFY_HARD_DRIVE,
            vm_object
        )
        self.get_object(id_).get_config_object().delete()

    def _get_available_storage_types(self):
        """Returns a list of storage types that are available on the node."""
        available_storage_types = []
        storage_factory = self._get_registered_object('storage_factory')
        node_drbd = self._get_registered_object('node_drbd')
        for storage_type in self.get_all_storage_types():
            if storage_type.isAvailable(storage_factory, node_drbd):
                available_storage_types.append(storage_type)
        return available_storage_types

    def get_all_storage_types(self):
        """Returns the available storage types that MCVirt provides."""
        return get_all_submodules(Base)

    @Expose()
    def get_hard_drive_list_table(self):
        """Return a table of hard drives."""
        # Manually set permissions asserted, as this function can
        # run high privilege calls, but doesn't not require
        # permission checking
        self._get_registered_object('auth').set_permission_asserted()

        # Create table and set headings
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('ID', 'Size', 'Type', 'Storage Backend', 'Virtual Machine'))
        table.set_cols_width((50, 15, 15, 50, 20))

        # Obtain hard ives and add to table
        for hard_drive_obj in self.get_all():
            vm_object = hard_drive_obj.get_virtual_machine()
            hdd_type = ''
            storage_backend_id = 'Storage backend does not exist'
            try:
                storage_backend_id = hard_drive_obj.storage_backend.id_
                hdd_type = hard_drive_obj.get_type()
                hdd_size = SizeConverter(hard_drive_obj.get_size()).to_string()
            except (VolumeDoesNotExistError,
                    HardDriveDoesNotExistException,
                    StorageBackendDoesNotExist), exc:
                hdd_size = str(exc)

            table.add_row((hard_drive_obj.id_, hdd_size,
                           hdd_type, storage_backend_id,
                           vm_object.get_name() if vm_object else 'Not attached'))
        return table.draw()

    def get_all(self):
        """Return all hard drive objects."""
        return [self.get_object(id_) for id_ in HardDriveConfig.get_global_config().keys()]

    def getClass(self, storage_type, allow_base=False):
        """Obtains the hard drive class for a given storage type."""
        # If allowed to return base class and storage_type is
        # null, return the base class
        if allow_base and not storage_type:
            return Base

        for hard_drive_class in self.get_all_storage_types():
            if storage_type == hard_drive_class.__name__:
                return hard_drive_class
        raise UnknownStorageTypeException(
            'Attempted to initialise an unknown storage type: %s' %
            (storage_type)
        )

    @Expose()
    def get_drbd_object_by_resource_name(self, resource_name):
        """Obtains a hard drive object for a Drbd drive, based on the resource name."""
        node_drbd = self._get_registered_object('node_drbd')
        for hard_drive_object in node_drbd.get_all_drbd_hard_drive_object():
            if hard_drive_object.resource_name == resource_name:
                return hard_drive_object
        raise HardDriveDoesNotExistException(
            'Drbd hard drive with resource name \'%s\' does not exist' %
            resource_name
        )

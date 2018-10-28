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

from texttable import Texttable
from os.path import exists as os_path_exists
from os import makedirs
from enum import Enum

from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.config.virtual_machine import VirtualMachine as VirtualMachineConfig
from mcvirt.config.mcvirt import MCVirt as MCVirtConfig
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import (InvalidNodesException, DrbdNotEnabledOnNode,
                               InvalidVirtualMachineNameException, VmAlreadyExistsException,
                               ClusterNotInitialisedException, NodeDoesNotExistException,
                               VmDirectoryAlreadyExistsException, InvalidGraphicsDriverException,
                               MCVirtTypeError, VirtualMachineDoesNotExistException)
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose, Transaction
from mcvirt.utils import get_hostname
from mcvirt.argument_validator import ArgumentValidator
from mcvirt.virtual_machine.hard_drive.base import Driver as HardDriveDriver
from mcvirt.constants import AutoStartStates
from mcvirt.syslogger import Syslogger
from mcvirt.size_converter import SizeConverter


class GraphicsDriver(Enum):
    """Enums for specifying the graphics driver type"""

    VGA = 'vga'
    CIRRUS = 'cirrus'
    VMVGA = 'vmvga'
    XEN = 'xen'
    VBOX = 'vbox'
    QXL = 'qxl'


class Factory(PyroObject):
    """Class for obtaining virtual machine objects"""

    OBJECT_TYPE = 'virtual machine'
    VIRTUAL_MACHINE_CLASS = VirtualMachine
    DEFAULT_GRAPHICS_DRIVER = GraphicsDriver.VMVGA.value
    CACHED_OBJECTS = {}
    CACHED_SERIAL_OBJECTS = {}

    def autostart(self, start_type=AutoStartStates.ON_POLL):
        """Autostart VMs"""
        Syslogger.logger().info('Starting autostart: %s' % start_type.name)
        for vm in self.getAllVirtualMachines():
            try:
                    if (vm.isRegisteredLocally() and vm.is_stopped and
                            vm._get_autostart_state() in
                            [AutoStartStates.ON_POLL, AutoStartStates.ON_BOOT] and
                            (start_type == vm._get_autostart_state() or
                             start_type == AutoStartStates.ON_BOOT)):
                        try:
                            Syslogger.logger().info('Autostarting: %s' % vm.get_name())
                            vm.start()
                            Syslogger.logger().info('Autostart successful: %s' % vm.get_name())
                        except Exception, e:
                            Syslogger.logger().error('Failed to autostart: %s: %s' %
                                                     (vm.get_name(), str(e)))
            except Exception, exc:
                Syslogger.logger().error('Failed to get VM state: %s: %s' % (
                    vm.get_name(), str(exc)))
        Syslogger.logger().info('Finished autostsart: %s' % start_type.name)

    def get_remote_object(self,
                          node=None,     # The name of the remote node to connect to
                          node_object=None):   # Otherwise, pass a remote node connection
        """Obtain an instance of the virtual machine factory on a remote node"""
        cluster = self._get_registered_object('cluster')
        if node_object is None:
            node_object = cluster.get_remote_node(node)

        return node_object.get_connection('virtual_machine_factory')

    @Expose()
    def getVirtualMachineByName(self, vm_name):
        """Obtain a VM object, based on VM name"""
        ArgumentValidator.validate_hostname(vm_name)
        name_id_dict = {
            val['name']: key
            for key, val in VirtualMachineConfig.get_global_config()
        }
        if vm_name not in name_id_dict:
            raise VirtualMachineDoesNotExistException(
                'Error: Virtual Machine does not exist: %s' % vm_name
            )

        return self.get_virtual_machine_by_id(name_id_dict[vm_name])

    @Expose()
    def get_virtual_machine_by_id(self, vm_id):
        """Obtain a VM object, based on VM name"""
        # Validate VM ID
        ArgumentValidator.validate_id(vm_id, self)

        # Determine if VM object has been cached
        if vm_id not in Factory.CACHED_OBJECTS:
            # If not, create object, register with pyro
            # and store in cached object dict
            vm_object = VirtualMachine(self, vm_id)
            self._register_object(vm_object)
            vm_object.initialise()
            Factory.CACHED_OBJECTS[vm_id] = vm_object
        # Return the cached object
        return Factory.CACHED_OBJECTS[vm_id]

    @Expose()
    def getAllVirtualMachines(self, node=None):
        """Return objects for all virtual machines"""
        return [self.get_virtual_machine_by_id(vm_id) for vm_id in self.get_all_vm_ids(node=node)]

    @Expose()
    def get_all_vm_ids(self, node=None):
        """Get all VM IDs"""
        return VirtualMachineConfig.get_global_config().keys()

    @Expose()
    def getAllVmNames(self, node=None):
        """Returns a list of all VMs within the cluster or those registered on a specific node"""
        if node is not None:
            ArgumentValidator.validate_hostname(node)

        # If no node was defined, check the local configuration for all VMs
        if node is None:
            return [vm['name'] for vm in VirtualMachineConfig.get_global_config().values()]

        elif node == get_hostname():
            # @TODO - Why is this using libvirt?! Should use
            #         VM objects (i.e. config file to determine)
            #         and use a seperate function to get libvirt
            #         registered VMs
            # Obtain array of all domains from libvirt
            all_domains = self._get_registered_object(
                'libvirt_connector').get_connection().listAllDomains()
            return [vm.name() for vm in all_domains]

        else:
            # Return list of VMs registered on remote node
            cluster = self._get_registered_object('cluster')

            def remote_command(node_connection):
                """Get virtual machine names from remote node"""
                virtual_machine_factory = node_connection.get_connection('virtual_machine_factory')
                return virtual_machine_factory.getAllVmNames(node=node)
            return cluster.run_remote_command(callback_method=remote_command, nodes=[node])[node]

    @Expose()
    def listVms(self, include_ram=False, include_cpu=False, include_disk=False):
        """Lists the VMs that are currently on the host"""
        # Create base table
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)

        # Add headers
        headers = ['VM Name', 'State', 'Node']
        if include_ram:
            headers.append('RAM Allocation')
        if include_cpu:
            headers.append('CPU')
        if include_disk:
            headers.append('Total disk size (MiB)')

        table.header(tuple(headers))

        # Iterate over VMs and add to list
        for vm_object in sorted(self.getAllVirtualMachines(), key=lambda vm: vm.name):
            vm_row = [vm_object.get_name(), vm_object._getPowerState().name,
                      vm_object.getNode() or 'Unregistered']
            if include_ram:
                vm_row.append(str(int(vm_object.getRAM()) / 1024) + 'MB')
            if include_cpu:
                vm_row.append(vm_object.getCPU())
            if include_disk:
                hard_drive_size = 0
                for disk_object in vm_object.getHardDriveObjects():
                    hard_drive_size += disk_object.getSize()
                vm_row.append(hard_drive_size)
            table.add_row(vm_row)
        table_output = table.draw()
        return table_output

    @Expose()
    def check_exists(self, vm_name):
        """Determines if a VM exists, given a name"""
        try:
            ArgumentValidator.validate_hostname(vm_name)
        except (MCVirtTypeError, InvalidVirtualMachineNameException):
            return False

        return vm_name in self.getAllVmNames()

    @Expose()
    def checkName(self, name, ignore_exists=False):
        try:
            ArgumentValidator.validate_hostname(name)
        except MCVirtTypeError:
            raise InvalidVirtualMachineNameException(
                'Error: Invalid VM Name - VM Name can only contain 0-9 a-Z and dashes'
            )

        if len(name) < 3:
            raise InvalidVirtualMachineNameException('VM Name must be at least 3 characters long')

        if self.check_exists(name) and not ignore_exists:
            raise VmAlreadyExistsException('VM already exists')

        return True

    def ensure_graphics_driver_valid(self, driver):
        """Check that the provided graphics driver name is valid"""
        if driver not in [i.value for i in list(GraphicsDriver)]:
            raise InvalidGraphicsDriverException('Invalid graphics driver \'%s\'' % driver)

    def _pre_create_checks(self, required_storage_size=None, networks=None,
                           storage_type=None, nodes=None, storage_backend=None):
        """Perform pre-creation checks on VM. Ensure that all networks exist,
        storage backend is valid etc. As well as ensuring that the VM can be run
        on the required nodes (or at least one node if not specified).
        This is used to ensure that all requested options for a hypothetical VM is possible,
        before a VM is created.
        """
        networks = [] if networks is None else networks

        cluster = self._get_registered_object('cluster')

        # Ensure all nodes are valid, if defined
        if nodes:
            for node in nodes:
                cluster.ensure_node_exists(node, include_local=True)

        # Determine if the list of nodes is a pre-defined list by the user, or
        # list of all nodes
        nodes_predefined = (nodes is not None and len(nodes))

        # If nodes has not been defined, get a list of all
        if not nodes:
            nodes = cluster.get_nodes(return_all=True, include_local=True)

        # If defined, ensure that all networks exist
        if networks:
            for network in networks:
                network_factory = self._get_registered_object('network_factory')
                network_factory.ensure_exists(network)

                # Obtain network object
                network = network_factory.get_network_by_name(network)

                # Go through each of the nodes and determine if the network
                # if available on the node
                for node in nodes:
                    # If the list was pre-defined by the user, the network
                    # MUST be available to all nodes, otherwise.
                    if nodes_predefined:
                        network.ensure_available_on_node(node)

                    # Otherwise, if the network is not available on the
                    # node, remove the node from list of available nodes.
                    elif not network.check_available_on_node(node):
                        if node in nodes:
                            nodes.remove(node)

        if required_storage_size:
            # Use the hard drive factory to determine whether the given
            # storage requirements are possible, given the available nodes.
            hard_drive_factory = self._get_registered_object('hard_drive_factory')
            nodes, storage_type, storage_backend = hard_drive_factory.ensure_hdd_valid(
                size=required_storage_size, storage_type=storage_type, nodes=nodes,
                storage_backend=storage_backend, nodes_predefined=nodes_predefined
            )

        return nodes, storage_backend, storage_type

    @Expose(locking=True, instance_method=True)
    def create(self, *args, **kwargs):
        """Exposed method for creating a VM, that performs a permission check"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.CREATE_VM)
        return self._create(*args, **kwargs)

    def _create(self,
                name, cpu_cores, memory_allocation,  # Basic details, name etc.
                hard_drives=None,  # List of hard drive sizes to be created
                network_interfaces=None,  # List of networks to create network interfaces
                                          # to attach to
                node=None,  # The node to initially register the VM on
                available_nodes=None,  # List of nodes that the VM will be availble to.
                                       # For DRBD, this will be the two nodes
                                       # that DRBD is setup on. For other storage types,
                                       # it will be the nodes that the VM 'MUST' be
                                       # compatible with, i.e. storage backend must span
                                       # across them and networks exist on all nodes.
                storage_type=None,  # Storage type (string)
                hard_drive_driver=None, graphics_driver=None, modification_flags=None,
                storage_backend=None,   # Storage backend to be used. If not specified,
                                        # will default to an available storage backend,
                                        # if only 1 is avaiallbe.
                is_static=None):  # Manually override whether the VM is marked as static
        """Create a VM and returns the virtual_machine object for it"""
        # @TODO: Does this method need to do EVERYTHING?
        #       Maybe it should create the BARE MINIMUM required for a VM
        #       and leave it up to the parser to create everything else.
        #       The benefit to doing it in one function is to be able to
        #       validate that everything will work before-hand.

        # Set iterative items to empty array if not specified.
        # Can't set these to empty arrays by default, as if we attempt to append to them,
        # it will alter the default array (since it will be a reference)!
        network_interfaces = [] if network_interfaces is None else network_interfaces
        hard_drives = [] if hard_drives is None else hard_drives
        nodes_predefined = available_nodes is not None
        available_nodes = [] if available_nodes is None else available_nodes
        modification_flags = [] if modification_flags is None else modification_flags

        # Convert memory and disk sizes to bytes
        hard_drives = [hdd_size
                       if isinstance(hdd_size, int) else
                       SizeConverter.from_string(hdd_size, storage=True).to_bytes()
                       for hdd_size in hard_drives]
        memory_allocation = (memory_allocation
                             if memory_allocation is isinstance(memory_allocation, int) else
                             SizeConverter.from_string(memory_allocation).to_bytes())

        if storage_backend:
            storage_backend = self._convert_remote_object(storage_backend)

        # Ensure name is valid, as well as other attributes
        self.checkName(name)
        ArgumentValidator.validate_positive_integer(cpu_cores)
        ArgumentValidator.validate_positive_integer(memory_allocation)
        for hard_drive in hard_drives:
            ArgumentValidator.validate_positive_integer(hard_drive)
        if network_interfaces:
            for network_interface in network_interfaces:
                ArgumentValidator.validate_network_name(network_interface)
        if node is not None:
            ArgumentValidator.validate_hostname(node)
        for available_node in available_nodes:
            ArgumentValidator.validate_hostname(available_node)

        cluster_object = self._get_registered_object('cluster')
        local_hostname = get_hostname()

        if node and available_nodes and node not in available_nodes:
            raise InvalidNodesException('Node must be in available nodes')

        total_storage_size = sum(hard_drives) if hard_drives else None
        available_nodes, storage_backend, storage_type = self._pre_create_checks(
            required_storage_size=total_storage_size,
            networks=network_interfaces,
            storage_type=storage_type,
            nodes=available_nodes,
            storage_backend=storage_backend
        )

        # If a node has not been specified, assume the local node
        if node is None:
            node = local_hostname

        # Ensure that the local node is included in the list of available nodes
        if self._is_cluster_master and local_hostname not in available_nodes:
            raise InvalidNodesException('Local node must included in available nodes')

        # Ensure storage_type is a valid type, if specified
        hard_drive_factory = self._get_registered_object('hard_drive_factory')
        assert storage_type in [None] + [
            storage_type_itx.__name__ for storage_type_itx in self._get_registered_object(
                'hard_drive_factory').getStorageTypes()
        ]

        # Obtain the hard drive driver enum from the name
        if hard_drive_driver is not None:
            HardDriveDriver[hard_drive_driver]

        # If no graphics driver has been specified, set it to the default
        if graphics_driver is None:
            graphics_driver = self.DEFAULT_GRAPHICS_DRIVER

        # Check the driver name is valid
        self.ensure_graphics_driver_valid(graphics_driver)

        # Ensure the cluster has not been ignored, as VMs cannot be created with MCVirt running
        # in this state
        if self._cluster_disabled:
            raise ClusterNotInitialisedException('VM cannot be created whilst the cluster' +
                                                 ' is not initialised')

        # Determine if VM already exists
        if self.check_exists(name):
            raise VmAlreadyExistsException('Error: VM already exists')

        # Create directory for VM on the local and remote nodes
        if os_path_exists(VirtualMachine.get_vm_dir(name)):
            raise VmDirectoryAlreadyExistsException('Error: VM directory already exists')

        if local_hostname not in available_nodes and self._is_cluster_master:
            raise InvalidNodesException('One of the nodes must be the local node')

        # Create VM configuration file
        # This is hard coded method of determining is_static, as seen in hard drive object
        # @TODO Refactor into method that's shared with is_static
        config_nodes = (None
                        if ((storage_backend and storage_backend.shared and
                             storage_type == 'Local') or
                            (is_static is not None and not is_static))
                        else available_nodes)

        # Start transaction
        t = Transaction()

        vm_object = self.create_config(
            name, config_nodes, cpu_cores, memory_allocation, graphics_driver,
            nodes=self._get_registered_object('cluster').get_nodes(include_local=True))

        if node == get_hostname():
            # Register VM with LibVirt. If MCVirt has not been initialised on this node,
            # do not set the node in the VM configuration, as the change can't be
            # replicated to remote nodes
            vm_object._register(set_node=self._is_cluster_master)
        elif self._is_cluster_master:
            # If MCVirt has been initialised on this node and the local machine is
            # not the node that the VM will be registered on, set the node on the VM
            vm_object._setNode(node)

        if self._is_cluster_master:
            # Create disk images
            hard_drive_factory = self._get_registered_object('hard_drive_factory')
            for hard_drive_size in hard_drives:
                hard_drive_factory.create(vm_object=vm_object, size=hard_drive_size,
                                          storage_type=storage_type, driver=hard_drive_driver,
                                          storage_backend=storage_backend,
                                          nodes=available_nodes)

            # If any have been specified, add a network configuration for each of the
            # network interfaces to the domain XML
            network_adapter_factory = self._get_registered_object('network_adapter_factory')
            network_factory = self._get_registered_object('network_factory')
            if network_interfaces is not None:
                for network in network_interfaces:
                    network_object = network_factory.get_network_by_name(network)
                    network_adapter_factory.create(vm_object, network_object)

            # Add modification flags
            vm_object._update_modification_flags(add_flags=modification_flags)

        t.finish()

        return vm_object

    @Expose(remote_nodes=True)
    def create_config(self, name, config_nodes, cpu_cores, memory_allocation,
                      graphics_driver):
        """Create required VM configs"""
        # Create directory for VM
        makedirs(VirtualMachine.get_vm_dir(name))

        # Add VM to MCVirt configuration
        def update_mcvirt_config(config):
            """Add VM to global MCVirt config"""
            config['virtual_machines'].append(name)
        MCVirtConfig().update_config(
            update_mcvirt_config,
            'Adding new VM \'%s\' to global MCVirt configuration' %
            name)

        VirtualMachineConfig.create(name, config_nodes, cpu_cores, memory_allocation,
                                    graphics_driver)

        # Obtain an object for the new VM, to use to create disks/network interfaces
        vm_object = self.getVirtualMachineByName(name)
        vm_object.get_config_object().gitAdd('Created VM \'%s\'' % vm_object.get_name())
        return vm_object

    def undo__create_config(self, name, *args, **kwargs):
        """Remove any directories or configs that were created for VM"""
        pass

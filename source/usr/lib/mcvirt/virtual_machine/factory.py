import Pyro4
from texttable import Texttable
import re
from os.path import exists as os_path_exists
from os import makedirs

from virtual_machine import VirtualMachine
from virtual_machine_config import VirtualMachineConfig
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.cluster.cluster import Cluster
from mcvirt.node.drbd import DRBD as NodeDRBD
from mcvirt.virtual_machine.hard_drive.config.base import Base as HardDriveConfigBase
from mcvirt.virtual_machine.hard_drive.factory import Factory as HardDriveFactory
from mcvirt.auth.auth import Auth
from mcvirt.node.network.factory import Factory as NetworkFactory
from mcvirt.virtual_machine.network_adapter import NetworkAdapter
from mcvirt.exceptions import (StorageTypeNotSpecified, InvalidNodesException,
                               InvalidVirtualMachineNameException, VmAlreadyExistsException,
                               ClusterNotInitialisedException, NodeDoesNotExistException,
                               DRBDNotEnabledOnNode)
from mcvirt.rpc.lock import lockingMethod
from mcvirt.rpc.pyro_object import PyroObject


class Factory(PyroObject):
    """Class for obtaining virtual machine objects"""

    OBJECT_TYPE = 'virtual machine'

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    @Pyro4.expose()
    def getVirtualMachineByName(self, vm_name):
        """Obtain a VM object, based on VM name"""
        vm_object = VirtualMachine(self.mcvirt_instance, vm_name)
        self._register_object(vm_object)
        return vm_object

    @Pyro4.expose()
    def getAllVirtualMachines(self):
        """Return objects for all virtual machines"""
        return [self.getVirtualMachineByName(vm_name) for vm_name in self.getAllVmNames()]

    def getAllVmNames(self, node=None):
        """Returns a list of all VMs within the cluster or those registered on a specific node"""
        from mcvirt.cluster.cluster import Cluster
        # If no node was defined, check the local configuration for all VMs
        if (node is None):
            return MCVirtConfig().getConfig()['virtual_machines']
        elif (node == Cluster.getHostname()):
            # Obtain array of all domains from libvirt
            all_domains = self.mcvirt_instance.getLibvirtConnection().listAllDomains()
            return [vm.name() for vm in all_domains]
        else:
            # Return list of VMs registered on remote node
            cluster_instance = Cluster(self.mcvirt_instance)
            node = cluster_instance.getRemoteNode(node)
            return node.runRemoteCommand('virtual_machine-getAllVms', {})

    @Pyro4.expose()
    def listVms(self):
        """Lists the VMs that are currently on the host"""
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('VM Name', 'State', 'Node'))

        for vm_object in self.getAllVirtualMachines():
            table.add_row((vm_object.getName(), vm_object._getPowerState().name,
                           vm_object.getNode() or 'Unregistered'))
        return table.draw()

    @Pyro4.expose()
    def checkExists(self, vm_name):
        """Determines if a VM exists, given a name"""
        return (vm_name in self.getAllVmNames())

    @Pyro4.expose()
    def checkName(self, name):
        valid_name_re = re.compile(r'[^a-z^0-9^A-Z-]').search
        if (bool(valid_name_re(name))):
            raise InvalidVirtualMachineNameException(
                'Error: Invalid VM Name - VM Name can only contain 0-9 a-Z and dashes'
            )

        if len(name) < 3:
            raise InvalidVirtualMachineNameException('VM Name must be at least 3 characters long')

        if self.checkExists(name):
            raise InvalidVirtualMachineNameException('VM already exists')

        return True

    @Pyro4.expose()
    @lockingMethod(instance_method=True)
    def create(self, *args, **kwargs):
        """Creates a VM and returns the virtual_machine object for it"""
        return self._create(*args, **kwargs)

    def _create(self, name, cpu_cores, memory_allocation, hard_drives=[],
               network_interfaces=[], node=None, available_nodes=[], storage_type=None,
               auth_check=True, hard_drive_driver=None):
        """Creates a VM and returns the virtual_machine object for it"""
        if (auth_check):
            self.mcvirt_instance.getAuthObject().assertPermission(Auth.PERMISSIONS.CREATE_VM)

        # Validate the VM name
        valid_name_re = re.compile(r'[^a-z^0-9^A-Z-]').search
        if (bool(valid_name_re(name))):
            raise InvalidVirtualMachineNameException(
                'Error: Invalid VM Name - VM Name can only contain 0-9 a-Z and dashes'
            )

        # Ensure the cluster has not been ignored, as VMs cannot be created with MCVirt running
        # in this state
        if (self.mcvirt_instance.ignore_failed_nodes):
            raise ClusterNotInitialisedException('VM cannot be created whilst the cluster' +
                                                 ' is not initialised')

        # Determine if VM already exists
        if (VirtualMachine._checkExists(self.mcvirt_instance, name)):
            raise VmAlreadyExistsException('Error: VM already exists')

        # If a node has not been specified, assume the local node
        if (node is None):
            node = Cluster.getHostname()

        # If DRBD has been chosen as a storage type, ensure it is enabled on the node
        if (storage_type == 'DRBD' and not NodeDRBD.isEnabled()):
            raise DRBDNotEnabledOnNode('DRBD is not enabled on this node')

        # Create directory for VM on the local and remote nodes
        if (os_path_exists(VirtualMachine.getVMDir(name))):
            raise VmDirectoryAlreadyExistsException('Error: VM directory already exists')

        # If available nodes has not been passed, assume the local machine is the only
        # available node if local storage is being used. Use the machines in the cluster
        # if DRBD is being used
        cluster_object = Cluster(self.mcvirt_instance)
        all_nodes = cluster_object.getNodes()
        all_nodes.append(Cluster.getHostname())
        if (len(available_nodes) == 0):
            if (storage_type == 'DRBD' and self.mcvirt_instance.initialiseNodes()):
                # If the available nodes are not specified, use the
                # nodes in the cluster
                available_nodes = all_nodes
            else:
                # For local VMs, only use the local node as the available nodes
                available_nodes = [Cluster.getHostname()]

        # If there are more than the maximum number of DRBD machines in the cluster,
        # add an option that forces the user to specify the nodes for the DRBD VM
        # to be added to
        if (storage_type == 'DRBD' and len(available_nodes) != NodeDRBD.CLUSTER_SIZE):
            raise InvalidNodesException('Exactly two nodes must be specified')

        for check_node in available_nodes:
            if (check_node not in all_nodes):
                raise NodeDoesNotExistException('Node \'%s\' does not exist' % check_node)

        if (Cluster.getHostname() not in available_nodes and self.mcvirt_instance.initialiseNodes()):
            raise InvalidNodesException('One of the nodes must be the local node')

        # Create directory for VM
        makedirs(VirtualMachine.getVMDir(name))

        # Add VM to MCVirt configuration
        def updateMCVirtConfig(config):
            config['virtual_machines'].append(name)
        MCVirtConfig().updateConfig(
            updateMCVirtConfig,
            'Adding new VM \'%s\' to global MCVirt configuration' %
            name)

        # Create VM configuration file
        VirtualMachineConfig.create(name, available_nodes, cpu_cores, memory_allocation)

        # Add VM to remote nodes
        if (self.mcvirt_instance.initialiseNodes()):
            cluster_object.runRemoteCommand('virtual_machine-create',
                                            {'vm_name': name,
                                             'memory_allocation': memory_allocation,
                                             'cpu_cores': cpu_cores,
                                             'node': node,
                                             'available_nodes': available_nodes})

        # Obtain an object for the new VM, to use to create disks/network interfaces
        vm_object = self.getVirtualMachineByName(name)
        vm_object.getConfigObject().gitAdd('Created VM \'%s\'' % vm_object.getName())

        if (node == Cluster.getHostname()):
            # Register VM with LibVirt. If MCVirt has not been initialised on this node,
            # do not set the node in the VM configuration, as the change can't be
            # replicated to remote nodes
            vm_object._register(set_node=self.mcvirt_instance.initialiseNodes())
        elif (self.mcvirt_instance.initialiseNodes()):
            # If MCVirt has been initialised on this node and the local machine is
            # not the node that the VM will be registered on, set the node on the VM
            vm_object._setNode(node)

        if (self.mcvirt_instance.initialiseNodes()):
            # Create disk images
            hard_drive_factory = HardDriveFactory(self.mcvirt_instance)
            for hard_drive_size in hard_drives:
                hard_drive_factory._create(vm_object=vm_object, size=hard_drive_size,
                                           storage_type=storage_type, driver=hard_drive_driver)

            # If any have been specified, add a network configuration for each of the
            # network interfaces to the domain XML
            if (network_interfaces is not None):
                for network in network_interfaces:
                    network_factory = NetworkFactory(self.mcvirt_instance)
                    network_object = network_factory.getNetworkByName(network)
                    vm_object._createNetworkAdapter(vm_object, network_object)

        return vm_object

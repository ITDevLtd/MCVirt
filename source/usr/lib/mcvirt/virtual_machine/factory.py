import Pyro4
from mcvirt.mcvirt_config import MCVirtConfig
from mcvirt.cluster.cluster import Cluster

class Factory(object):
    """Class for obtaining virtual machine objects"""

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    @Pyro4.expose()
    def getVirtualMachineByName(self, vm_name):
        """Obtain a VM object, based on VM name"""
        vm_object = VirtualMachine(self.mcvirt_instance, vm_name, self._pyroDaemon)
        if self._pyroDaemon:
            self._pyroDaemon.register(vm_object)
        return vm_object

    @Pyro4.expose()
    def getAllVirtualMachines(self):
        """Return objects for all virtual machines"""
        return [self.getVirtualMachineByName(vm_name) for vm_name in self.getallVmNames()]

    def getallVmNames(self, node=None):
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

import Pyro4
from texttable import Texttable

from virtual_machine import VirtualMachine
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
        vm_object = VirtualMachine(self.mcvirt_instance, vm_name)
        if self._pyroDaemon:
            self._pyroDaemon.register(vm_object)
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
            table.add_row((vm_object.getName(), vm_object.getPowerState(enum=True).name,
                           vm_object.getNode() or 'Unregistered'))
        return table.draw()

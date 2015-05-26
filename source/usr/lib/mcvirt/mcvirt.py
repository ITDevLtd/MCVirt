#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import libvirt
import sys
import os
from lockfile import FileLock
from texttable import Texttable
import socket

from mcvirt_config import MCVirtConfig

class MCVirt:
    """Provides general MCVirt functions"""

    TEMPLATE_DIR = '/usr/lib/mcvirt/templates'
    BASE_STORAGE_DIR = '/var/lib/mcvirt'
    NODE_STORAGE_DIR = BASE_STORAGE_DIR + '/' + socket.gethostname()
    BASE_VM_STORAGE_DIR = NODE_STORAGE_DIR + '/vm'
    ISO_STORAGE_DIR = NODE_STORAGE_DIR + '/iso'
    LOCK_FILE_DIR = '/var/run/lock/mcvirt'
    LOCK_FILE = LOCK_FILE_DIR + '/lock'

    def __init__(self, uri=None, initialise_nodes=True, username=None):
        """Checks lock file and performs initial connection to libvirt"""
        self.libvirt_uri = uri
        self.connection = None
        # Create an MCVirt config instance and force an upgrade
        config_instance = MCVirtConfig(perform_upgrade=True, mcvirt_instance=self)

        # Configure custom username - used for unittests
        self.ignore_drbd = False
        self.username = username

        # Cluster configuration
        self.initialise_nodes = initialise_nodes
        self.remote_nodes = {}

        self.obtained_filelock = False
        self.lockfile_object = None
        self.obtainLock()

        # Create cluster instance, which will initialise the nodes
        from cluster.cluster import Cluster
        Cluster(self)

        # Connect to LibVirt
        self.getLibvirtConnection()

    def __del__(self):
        """Removes MCVirt lock file on object destruction"""
        # Disconnect from each of the nodes
        for connection in self.remote_nodes:
            self.remote_nodes[connection] = None
        self.remote_nodes = {}

        # Remove lock file
        self.releaseLock()

    def obtainLock(self, timeout=2):
        """Obtains the MCVirt lock file"""
        # Create lock file, if it does not exist
        if (not os.path.isfile(self.LOCK_FILE)):
            if (not os.path.isdir(self.LOCK_FILE_DIR)):
                os.mkdir(self.LOCK_FILE_DIR)
            open(self.LOCK_FILE, 'a').close()

        # Attempt to lock lockfile
        if (not self.obtained_filelock and not self.lockfile_object):
            self.lockfile_object = FileLock(self.LOCK_FILE)

        # Check if lockfile object is already locked
        if (self.obtained_filelock or self.lockfile_object.is_locked()):
            raise MCVirtException('An instance of MCVirt is already running')

        try:
            self.lockfile_object.acquire(timeout=timeout)
            if (self.initialise_nodes):
                for remote_node in self.remote_nodes:
                    self.remote_nodes[remote_node].runRemoteCommand('mcvirt-obtainLock',
                                                                      {'timeout': timeout})

            self.obtained_filelock = True
        except:
            raise MCVirtException('An instance of MCVirt is already running')

    def releaseLock(self):
        """Releases the MCVirt lock file"""
        if (self.obtained_filelock):
            if (self.initialise_nodes):
                for remote_node in self.remote_nodes:
                    self.remote_nodes[remote_node].runRemoteCommand('mcvirt-releaseLock', {})
            self.lockfile_object.release()
            self.lockfile_object = None
            self.obtained_filelock = False

    def getLibvirtConnection(self):
        """
        Obtains a libvirt connection. If one does not exist,
        connect to libvirt and store the connection as an object variable.
        Exit if an error occurs whilst connecting.
        """
        if (self.connection == None):
            self.connection = libvirt.open(self.libvirt_uri)
            if (self.connection == None):
                raise MCVirtException('Failed to open connection to the hypervisor')
        return self.connection

    def initialiseNodes(self):
        """Returns the status of the MCVirt 'initialise_nodes' flag"""
        return self.initialise_nodes

    def getAuthObject(self):
        """Returns an instance of the Auth class"""
        from auth import Auth
        return Auth(self.username)

    def getAllVirtualMachineObjects(self):
        """Obtain array of all domains from libvirt"""
        from virtual_machine.virtual_machine import VirtualMachine
        all_vms = VirtualMachine.getAllVms(self)
        vm_objects = []
        for vm_name in all_vms:
            vm_objects.append(VirtualMachine(self, vm_name))

        return vm_objects

    def listVms(self):
        """Lists the VMs that are currently on the host"""
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('VM Name', 'State', 'Node'))

        for vm_object in self.getAllVirtualMachineObjects():
            table.add_row((vm_object.getName(), vm_object.getStateText(),
                           vm_object.getNode()))
        print table.draw()

    def printInfo(self):
        """Prints information about the nodes in the cluster"""
        from cluster.cluster import Cluster
        table = Texttable()
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        table.header(('Node', 'IP Address', 'Status'))
        cluster_object = Cluster(self)
        # Add this node to the table
        table.add_row((Cluster.getHostname(), cluster_object.getClusterIpAddress(),
                       'Local'))

        # Add remote nodes
        for node in cluster_object.getNodes():
            node_config = cluster_object.getNodeConfig(node)
            node_status = 'Unreachable'
            try:
                cluster_object.getRemoteNode(node)
                node_status = 'Connected'
            except:
                pass
            table.add_row((node, node_config['ip_address'],
                           node_status))
        print table.draw()

class MCVirtException(Exception):
    """Provides an exception to be thrown for errors in MCVirt"""
    pass

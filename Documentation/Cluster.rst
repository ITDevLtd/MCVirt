==========
Clustering
==========


Nodes running MCVirt can be joined together in a cluster - this allows the synchronization of VM/global configurations.

Only 2 nodes are currently supported in a cluster.



Viewing the status of a cluster
-------------------------------


To view the status of the cluster, run the following on an MCVirt node:

  ::
    
    sudo mcvirt info
    


This will show the cluster nodes, IP addresses, and status.



Adding a new node
-----------------


It is best to join a blank node (containing a default configuration without any VMs) to a cluster.

When a machine is connected to a cluster, it receives the permission/network/virtual machine configuration from the node connecting to it.

**Note:** Always run the mcvirt cluster add command from the source machine, containing VMs, connecting to a remote node that is blank.

The new node must be configured on separate network/VLAN for MCVirt cluster communication.

The IP address for this network must be stored in the MCVirt configuration file and can be retrieved from the machine, by running ``mcvirt info``.



Joining the node to the cluster
`````````````````````````````````````````````````````````````


**Note:** The following can only be performed by a superuser.

1. From the source node, run:

  ::
    
    sudo mcvirt cluster --add-node --node <Remote Node Name> --ip-address <Remote Cluster IP Address>
    

2. A prompt for the root password of the remote node will be presented.
3. The local node will connect to the remote node, ensure it is suitable as a remote node, setup authentication between the nodes and copy the local permissions/network/virtual machine configurations to the remote node.



Removing a node from the cluster
--------------------------------


**Note:** The following can only be performed by a superuser.

To the remove a node from the cluster, run:

  ::
    
    sudo mcvirt cluster remove-node --node <Remote Node Name>
    

Get Cluster information
-----------------------

* In order to view status information about the cluster, use the 'info' parameter for MCVirt, without specifying a VM name::

    sudo mcvirt info


Off-line migration
------------------

* VMs can be migrated to the other node in the cluster, whilst the VM is powered off, using::

    sudo mcvirt migrate --node <Destination node> <VM Name>

* Additional parameters are available to aid the migration and minimise downtime:
  * '--wait-for-shutdown', which will cause the migration command to poll the running state of the VM and migrate once the VM is in a powered off state, allowing the user to shutdown the VM from within the guest operating system.
  * '--start-after-migration', which starts the VM immediately after the migration has finished


====
DRBD
====

DRBD is used by McVirt to use replicate storage across a 2-node cluster.

Once DRBD is configured and the node is in a cluster, 'DRBD' can be specified when creating a VM, which allows the VM to be migrated between nodes.


Configuring DRBD
----------------

1. Ensure the package ``drbd8-utils`` is installed on both of the nodes in the cluster
2. Ensure that the IP to be used for DRBD traffic is configured in global MCVirt configuration, ``/var/lib/mcvirt/`hostname`/config.json``
3. Perform the following MCVirt command to configure DRBD::

    sudo mcvirt drbd --enable


DRBD verification
-----------------

MCVirt has the ability to start/monitor DRBD verifications (See the `DRBD documentation <https://drbd.linbit.com/users-guide/s-use-online-verify.html>`_.

The verification can be performed by using::

    sudo mcvirt verify <--all>|<VM Name>

This will perform a verification of the specified VM (or all of the DRBD-backed VMs, if '--all' is specified). Once the verification is complete, an exception is thrown if any of the verifications fail.

The status of the latest verification is captured and will stop users from starting/migrating the VM.

If the verification fails:

* The DRBD volume must be resynced (for more information, see the `DRBD documentation for re-syncing <https://drbd.linbit.com/users-guide/ch-troubleshooting.html>`_).
* Once this is complete, perform another MCVirt verification to mark the VM as in-sync, which will lift the limitations.

===============
Troubleshooting
===============
Failures during VM migration
----------------------------

If a VM migration fails, the VM maybe left in a state where it is not registered on either node in the cluster.

To re-register the node in the cluster, as root, perform the following (where the example VM name is 'test-vm'::

    root@node:~# python
    >>> import sys
    >>> sys.path.append('/usr/lib')
    >>> from mcvirt.mcvirt import MCVirt
    >>> mcvirt_instance = MCVirt()
    >>> from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    >>>
    >>> # Replace 'test-vm' with the name of the VM
    >>> vm_object = VirtualMachine(mcvirt_instance, 'test-vm')
    >>>
    >>> # Determine if the VM is definitiely not registered
    >>> vm_object.getNode() is None
    >>>
    >>> vm_object.register() # Register on local node

Failures during VM creation/deletion
------------------------------------

When a VM is created, the following order is performed:

1. The VM is created, configured with the name, memory allocation and number of CPU cores

2. The VM is then created on the remote node

3. The VM is then registered with LibVirt on the local node

4. The hard drive for the VM is created. (For DRBD-backed storage, the storage is created on both nodes and synced)

5. Any network adapters are added to the VM
 
If a failure of occurs during steps 4/5, the VM will still exist after the failure. The user should be able to see the VM, using ``mcvirt list``.
 
The user can re-create the disks/network adapters as necessary, using the ``mcvirt update`` command, using ``mcvirt info <VM Name>`` to monitor the virtual hardware that is attached to the VM.

DRBD hard drive creation failure
--------------------------------

If a failure occurs during the creation of the DRBD-backed hard drive, the following steps can be taken to manually remove it.

**Note:** These must be performed as root.

1. Assuming the creation failed, the hard drive will not have been added to VM configuration in LibVirt.

2. Start a python shell and initialise MCVirt::

    root@node:~# python
    >>> import sys
    >>> sys.path.append('/usr/lib')
    >>> from mcvirt.mcvirt import MCVirt
    >>> mcvirt_instance = MCVirt()

3. Determine if the disk is attached to the VM::

    >>> from mcvirt.virtual_machine.virtual_machine import VirtualMachine
    >>> vm_object = VirtualMachine(mcvirt_instance, '<VM Name>') # Replace <VM Name> with the name of the VM
    >>> len(vm_object.getDiskObjects())
    >>>
    >>> # The number returned is the number of hard disks attached to the VM.
    >>> # If this includes the disk that you wish to remove, perform the following
    >>> from mcvirt.virtual_machine.hard_drive.factory import Factory
    >>> Factory.getObject(vm_object, <Disk ID>).delete()

3. If the disk object was not found in the previous step, perform the following::

    >>> from mcvirt.virtual_machine.hard_drive.drbd import DRBD
    >>> # Replace <Disk ID> with the ID of the disk (1 for the first hard drive, 2 for the second etc.)
    >>> config_object = Factory.getConfigObject(vm_object, 'DRBD', '<Disk ID>')
    >>> from mcvirt.node.cluster import Cluster
    >>> cluster_instance = Cluster(mcvirt)
    >>> cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-drbdDown',
    ...                                   {'config': config_object._dumpConfig()})
    >>> DRBD._drbdDown(config_object)
    >>> cluster_instance.runRemoteCommand('virtual_machine-hard_drive-drbd-removeDrbdConfig',
    ...                                   {'config': config_object._dumpConfig()})
    >>> config_object._removeDrbdConfig()
    >>> raw_logical_volume_name = config_object._getLogicalVolumeName(config_object.DRBD_RAW_SUFFIX)
    >>> meta_logical_volume_name = config_object._getLogicalVolumeName(config_object.DRBD_META_SUFFIX)
    >>> DRBD._removeLogicalVolume(config_object, meta_logical_volume_name,
    ...                           perform_on_nodes=True)
    >>> DRBD._removeLogicalVolume(config_object, raw_logical_volume_name,
    ...                           perform_on_nodes=True)


Failures due to 'Another instance of MCVirt is running'
-------------------------------------------------------

If MCVirt complains that 'Another instance of MCVirt is running', the following can be performed as root:

1. Ensure that there are no instance actually running::

    root@node:~# ps aux  | grep mcvirt

2. Remove the lock files from the local node::

    root@node:~# rm -r /var/run/lock/mcvirt

3. Remove the lock files from the remote nodes, using the command in the previous step

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

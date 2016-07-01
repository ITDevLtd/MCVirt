==========
Clustering
==========


Nodes running MCVirt can be joined together in a cluster - this allows the synchronization of VM/global configurations.




Viewing the status of a cluster
-------------------------------


To view the status of the cluster, run the following on an MCVirt node:

  ::

    mcvirt info



This will show the cluster nodes, IP addresses, and status.



Adding a new node
-----------------


It is best to join a blank node (containing a default configuration without any VMs) to a cluster.

When a machine is connected to a cluster, it receives the permission/network/virtual machine configuration from the node connecting to it, and all existing data (VMs, users, permissions etc...) is removed.

**Note:** Always run the mcvirt cluster add command from the source machine, containing VMs, connecting to a remote node that is blank.

The new node must be configured on separate network/VLAN for MCVirt cluster communication.

The IP address that MCVirt clustering/DRBD communications will be performed over must be configured by performing the following on both nodes::

    mcvirt node --set-ip-address <Node cluster IP address>

This configuration can be retrieved by running ``mcvirt info``.


Joining the node to the cluster
`````````````````````````````````````````````````````````````


**Note:** The following can only be performed by a superuser.

1. From the remote node, run:

  ::

    mcvirt cluster get-connect-string

The connect string will be displayed

2. From the source node, run:

  ::

    mcvirt cluster add-node --connect-string <connect string>

where ``<connect string>`` is the string printed out in step 1.


3. The local node will connect to the remote node, ensure it is suitable as a remote node, setup authentication between the nodes and copy the local permissions/network/virtual machine configurations to the remote node. **Note:** All existing data on the remote node will be removed.

Removing a node from the cluster
--------------------------------


**Note:** The following can only be performed by a superuser.

To the remove a node from the cluster, run:

  ::

    mcvirt cluster remove-node --node <Remote Node Name>


Get Cluster information
-----------------------

* In order to view status information about the cluster, use the 'info' parameter for MCVirt, without specifying a VM name::

    mcvirt info


Virtual machine migration
-------------------------

* VMs that use DRBD-based storage can be migrated to the other node in the cluster, whilst the VM is powered off, using::

    mcvirt migrate --node <Destination node> <VM Name>

* Additional parameters are available to aid the migration and minimise downtime:

  * '--wait-for-shutdown', which will cause the migration command to poll the running state of the VM and migrate once the VM is in a powered off state, allowing the user to shutdown the VM from within the guest operating system.

  * '--start-after-migration', which starts the VM immediately after the migration has finished

  * '--online',  which will perform online migration

====
DRBD
====

DRBD is used by MCVirt to use replicate storage across a 2-node cluster.

Once DRBD is configured and the node is in a cluster, 'DRBD' can be specified as the storage type when creating a VM, which allows the VM to be migrated between nodes.


Configuring DRBD
----------------

1. Ensure the package ``drbd8-utils`` is installed on both of the nodes in the cluster
2. Ensure that the IP to be used for DRBD traffic is configured in global MCVirt configuration, ``/var/lib/mcvirt/`hostname`/config.json``
3. Perform the following MCVirt command to configure DRBD::

    mcvirt drbd --enable


DRBD verification
-----------------

MCVirt has the ability to start/monitor DRBD verifications (See the `DRBD documentation <https://drbd.linbit.com/users-guide/s-use-online-verify.html>`_).

The verification can be performed by using::

    mcvirt verify <--all>|<VM Name>

This will perform a verification of the specified VM (or all of the DRBD-backed VMs, if '--all' is specified). Once the verification is complete, an exception is thrown if any of the verifications fail.

The status of the latest verification is captured and will stop users from starting/migrating the VM.

If the verification fails:

* The DRBD volume must be resynced (for more information, see the `DRBD documentation for re-syncing <https://drbd.linbit.com/users-guide/ch-troubleshooting.html>`_).
* Once this is complete, perform another MCVirt verification to mark the VM as in-sync, which will lift the limitations.

===============
Troubleshooting
===============

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

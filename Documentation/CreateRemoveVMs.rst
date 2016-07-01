

Create/Remove VMs
------------------


* All commands must be performed on the MCVirt node, which can be accessed via SSH using LDAP credentials.

* You must be a superuser to create and remove VMs


Create VM
`````````````````


* Use the MCVirt utility to create VMs:

  ::

    mcvirt create '<VM Name>'


* The following parameters are available:

  * **--memory** - Amount of memory to allocate to the VM (MB) (required)

  * **--cpu-count** - Number of vCPUs to be allocated to the VM (required)

  * **--disk-size** - Size of initial disk to be added to the VM (MB) (optional)

  * **--network** - Provide the name of a network to be attached to the VM. (optional)

    * This can be called as multiple times.

    * A separate network interface is added to the VM for each network.

    * A network can be specified multiple times to create multiple adapters connected to the same network.

  * **--storage-type** - Storage backing type - either ``Local`` or ``DRBD``.

  * **--nodes** - Specifies the nodes that the VM will be hosted on, if a DRBD storage-type is specified and there are more than 2 nodes in the cluster.

  * **--driver** - The virtual disk driver to use. If this is not specified then MCVirt will select the most appropriate driver (optional)


Cloning a VM
````````````````````````


Cloning/duplicating a VM will create an identical replica of the VM.

Although both cloning and duplicating initially may appear to provide the same functionality, there are core differences, based on how they work, which should be noted to decide which function to use.

Both cloning and duplicating a VM can be performed by an **owner** of a VM.



Cloning
`````````````


* The hard disk for the VM is **snapshotted**, which means the VM is cloned very quickly
* Cloning VMs is not support for DRBD-backed VMs
* Some restrictions are imposed on both the parent and clone, due to the way that the storage is cloned:

  * Parent VMs cannot be:

    * Started

    * Resize (HDDs)

    * Deleted

  * VM Clones cannot be:

    * Resized

    * Cloned

  * **Note:** All restrictions are lifted once all VM clones have been removed.

A VM can be cloned by performing the following:

  ::

    mcvirt clone --template <Source VM Name> <Target VM Name>





Duplicating
`````````````````````


* Duplicating produces a new VM that is a completely separate entity to the source, meaning that no restrictions are imposed on either VM
* Duplicating a VM will copy the entire VM hard drive, which takes longer than cloning a VM

A VM can be duplicated by performing the following:

  ::

    mcvirt duplicate --template <Source VM Name> <Target VM Name>





Removing VM
`````````````````````


* Ensure that the VM is stopped.
* Use the MCVirt utility to remove the VM:

  ::

    mcvirt delete <VM Name>


* Without any parameters, the VM will simply be 'unregistered' from the node.
* To remove all data associated with the VM, supply the parameter **--remove-data**
* Only a superuser can delete a VM
=================
Create/Remove VMs
=================


All commands must be performed on the McVirt host, which can be accessed via SSH using LDAP credentials.


Create VM
=========


* Use the McVirt utility to create VMs:

  ::
    
    mcvirt create '<VM Name>'
    


* The following parameters are available:

  * **--memory** - Amount of memory to allocate to the VM (MB) (required)
  * **--disk-size** - Size of initial disk to be added to the VM (MB) (required)
  * **--cpu-count** - Number of vCPUs to be allocated to the VM (required)
  * **--network** - Provide the name of a network to be attached to the VM. (optional)

    * This can be called as multiple times.
    * A separate network interface is added to the VM for each network.
    * A network can be specified multiple times to create multiple adapters connected to the same network.




Cloning a VM
============


* Use the McVirt utility to clone VMs:

  ::
    
    mcvirt clone '<New VM Name>' --template '<Template VM Name>'

* **Note:** cloning a VM imposes the following restrictions:

  * Parent VMs cannot be:

    * Started
    * Resize (HDDs)
    * Deleted

  * VM Clones cannot be:

    * Resized
    * Cloned
  * All restrictions are lifted once all VM clones have been removed.



Removing VM
===========


* Ensure that the VM is stopped.
* Use the McVirt utility to remove the VM:

  ::
    
    mcvirt delete <VM Name>
* Without any parameters, the VM will simply be 'unregistered' from the host.
* To remove all data associated with the VM, supply the parameter **--remove-data**
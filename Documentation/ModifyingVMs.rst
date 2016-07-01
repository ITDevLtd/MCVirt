=============
Modifying VMs
=============




Increase Disk Size
````````````````````````````````````


* Power off the VM
* Use MCVirt to increase the size of the disk - you will need to find the disk ID, which can be found by looking at the VM configuration (in most cases where a VM has one disk attached to it, it should be 1):

  ::

    mcvirt update --increase-disk <Amount to increase (MB)> --disk-id <Disk Id> <VM Name>





Change Memory/CPU Allocation
````````````````````````````````````````````````````````


* Update the VM memory allocation and virtual CPU count using the following:

  ::

    mcvirt update --memory <New Memory Allocation (MB)> <VM Name>
    mcvirt update --cpu-count <New CPU count> <VM Name>



* The changes will take affect the next time the VM is booted. If the VM is running, it will need to be powered off and started again.



Add Additional Disk
`````````````````````````````````````


* Use the following MCVirt command to add an additional disk to a VM:

  ::

    mcvirt update --add-disk <Size of disk (MB)> <VM Name>


* The device will be attached to the VM the next time it's booted. If the VM is running, it will need to be powered off and started again.



Add/Remove Network Adapter
`````````````````````````````````````````````````````


* Use the following MCVirt command to add/remove network adapters to/from a VM

* Add an adapter:

  ::

    mcvirt update --add-network <Network Name> <VM Name>



* Remove an adapter:

  ::

    mcvirt update --remove-network '<NIC MAC Address>' <VM Name>


* Use the formatting '00:11:22:33:44:55' for the MAC address

* The device will altered the next time the VM is booted. If the VM is running, it will need to be powered off and started again.



Attaching ISO
`````````````````````````

* ISO images can be attached to the cdrom drive of a VM whilst booting the VM
* Use the MCVirt utility to start the VM, using the '--iso' parameter to define the ISO image to be attached to the VM::

    mcvirt start <VM Name> --iso <Name of ISO file>

* The ISO file must be stored within /var/lib/mcvirt/iso.


VM Locking
----------

VMs can be locked by superusers, which stops them from being started, stopped or migrated

* To lock a VM::

    mcvirt lock --lock <VM Name>

* To unlock a VM::

    mcvirt lock --unlock <VM Name>

* Users can check the lock status of a VM by running::

    mcvirt lock --check-lock <VM Name>


===============
Controlling VMs
===============


All commands must be performed on the MCVirt node, which can be accessed via SSH.



Start VM
--------


* Use the MCVirt utility to start VMs:

  ::

    mcvirt start <VM name>





Stop VM
-------


* Use the MCVirt utility to stop VMs:

  ::

    mcvirt stop <VM name>





Reset VM
--------


* Use the MCVirt utility to reset VMs:

  ::

    mcvirt reset <VM Name>


* Only a super user can reset a VM. Normal users can stop and start the VM.



Get VM information
------------------


* In order to view information about a VM, use the 'info' parameter for MCVirt:

  ::

    mcvirt info <VM Name>


* Example output:

  ::

    <Username>@node:~# mcvirt info test-vm
    Name              | test-vm
    CPU Cores         | 1
    Memory Allocation | 512MB
    State             | Running
    ISO location      | /var/lib/mcvirt/iso/ubuntu-12.04-server-amd64.iso
    -- Disk ID --     | -- Disk Size --
    1                 | 8GB
    -- MAC Address -- | -- Network --
    52:54:00:2b:8a:a1 | Production
    -- Group --       | -- Users --
    owner             | mc
    user              | nd





Listing virtual machines
------------------------


* In order to list the virtual machines on a node, run the following:

  ::

    mcvirt list


* This will provide the names of the virtual machines and their current state (running/stopped)



Connect to VNC
--------------


* By default, VMs are started with a VNC console, for which the port is automatically generated.
* The default listening IP address is 127.0.0.1, meaning that it can only be accessed from the node itself.

* To manually gain access to a VNC console, ssh to the node, forwarding the port:

  1. Determine the port that the VM is listening on:

     ::

      mcvirt info <VM Name> --vnc-port
      5904


  2. SSH onto the node, forwarding the port provided in the previous step (5904 in this case)

     * The local port can be any available port. In this example, 1232 is used:

     ::

      ssh <Username>@<Node> -L 1232:127.0.0.1:5904



     * For putty, use the tunnels configuration under **Connection -> SSH -> Tunnels**, where the source port is the local port and the destination is 127.0.0.1:<VNC Port>
  3. Use an VNC client to connect to 127.0.0.1:1232 on your local PC



Removing VNC display
--------------------


* By disabling the VNC display, a greater VM performance may be achieved.
* Power off the VM
* Perform:

  ::

    virsh edit <VM Name>


* Remove the ``<graphics type='vnc'...>...</graphics>`` lines from the configuration.
* Save the configuration and start the VM
* This can only be performed by root



Monitoring Resources
--------------------


* To monitor resources, the following commands are available that can be run from an SSH console:

  * top - monitor CPU/memory usages by processes

  * iftop - monitor network usage

  * iotop - monitor disk usages


Back up VM
----------

MCVirt can provide access to snapshots of the raw volumes of VM disks, allowing a superuser to backup the data

1. To create a snapshot, perform the following:

  ::

    mcvirt backup --create-snapshot --disk-id <Disk ID> <VM Name>

2. The returned path provides access to the disk at the time that the snapshot was created

**Warning:** The snapshot is 500MB in size, meaning that once the VM has changed 500MB of space on the disk, the VM will no longer be able to write to its disk

3. Once the data has been backed up, the snapshot can be removed by performing:

  ::

    mcvirt backup --delete-snapshot --disk-id <Disk ID> <VM Name>


* This can only be performed by a superuser
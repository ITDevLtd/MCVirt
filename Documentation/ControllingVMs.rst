===============
Controlling VMs
===============


* All commands must be performed on the MCVirt host, which can be accessed via SSH using LDAP credentials.



Start VM
--------


* Use the MCVirt utility to start VMs:

  ::
    
    sudo mcvirt start <VM name>
    




Stop VM
-------


* Use the MCVirt utility to stop VMs:

  ::
    
    sudo mcvirt stop <VM name>
    




Reset VM
--------


* Use virsh to reset VMs:

  ::
    
    virsh reset <VM Name>
    

* Only a super user can reset a VM. Normal users can stop and start the VM.



Get VM information
------------------


* In order to view information about a VM, use the 'info' parameter for MCVirt:

  ::
    
    sudo mcvirt info <VM Name>
    

* Example output:

  ::
    
    <Username>@host:~# mcvirt info test-vm
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


* In order to list the virtual machines on a host, run the following:

  ::
    
    sudo mcvirt list
    

* This will provide the names of the virtual machines and their current state (running/stopped)



Connect to VNC
--------------


* By default, VMs are started with a VNC console, for which the port is automatically generated.
* The default listening IP address is 127.0.0.1, meaning that it can only be accessed from the host itself.
* To access VNC, using the connect_vnc.pl script:

  ::
    
    connect_vnc.pl <VM Name>
    Username: <Username>
    Password:
    

* To manually gain access to a VNC console, ssh to the host, forwarding the port:

  1. Determine the port that the VM is listening on:

     ::
    
      sudo mcvirt info <VM Name> --vnc-port
      5904
    

  2. SSH onto the host, forwarding the port provided in the previous step (5904 in this case)

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
    

* Remove the <display type='vnc'... /> line from the configuration.
* Save the configuration and start the VM
* This can only be performed by a superuser



Monitoring Resources
--------------------


* To monitor resources, the following commands are available that can be run from an SSH console:

  * top - monitor CPU/memory usages by processes

  * iftop - monitor network usage

  * iotop - monitor disk usages



Back up VM
----------

* If the VM can be powered off:

  * Power off the VM

  * Login to <Node> as root

  * Ensure the LV of the HDD is active

  * Perform a dd of the HDD to a backup location:

  ::
    
    dd if=/dev/<Node>-vg/mcvirt_vm-test-vm5-disk-1 of=/path/to/backup/location.raw bs=1M
    

* This can only be performed by a superuser
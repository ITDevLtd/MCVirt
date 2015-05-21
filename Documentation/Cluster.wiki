==========
Clustering
==========


Nodes running McVirt can be joined together in a cluster - this allows the synchronization of VM/global configurations.



Viewing the status of a cluster
-------------------------------


To view the status of the cluster, run the following on an McVirt node:

  ::
    
    sudo mcvirt info
    


This will show the cluster nodes, IP addresses, and status.



Adding a new node
-----------------


It is best to join a blank node (containing a default configuration without any VMs) to a cluster.

When a machine is connected to a cluster, it receives the permission/network/virtual machine configuration from the node connecting to it.

**Note:** Always run the mcvirt cluster add command from the source machine, containing VMs, connecting to a remote node that is blank.

The new node must be configured on separate network/VLAN for McVirt cluster communication.

The IP address for this network must be stored in the McVirt configuration file and can be retrieved from the machine, by running ``mcvirt info``.



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
    

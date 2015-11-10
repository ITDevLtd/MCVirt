=============
Configuration
=============

Configure Network
-----------------

Remove default network
``````````````````````

* By default, libvirt configures a default network, 'default'.
* This can be removed by performing the following::

    sudo mcvirt network delete default

Creating/Removing Network
`````````````````````````

* Networks provide bridges between physical interfaces and virtual machines.
* To create a network on the node, perform the following as a superuser::

    sudo mcvirt network create <Network name> --interface <Physical interface>


* Assuming that there are not any VMs connected to a network, they can be removed using::

    sudo mcvirt network delete <Network name>

Configure MCVirt
-----------------

* The first time MCVirt is run, it creates a configuration file for itself, found in **/var/lib/mcvirt/<Hostname>/config.json**.
* The volume group, in which VM data will be stored as logical volumes, must be setup using::

    sudo mcvirt node --set-vm-vg <Volume Group>

* The cluster IP address must be configured if the node will be used in a cluster (See the `Cluster documentation <Cluster.rst>`_)::

    sudo mcvirt node --set-ip-address <Cluster IP Address>

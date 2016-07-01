=============
Configuration
=============

Configure Network
-----------------

Remove default network
``````````````````````

* By default, libvirt configures a default network, 'default'.
* The 'default' network is attached to a private network, which provides NAT routing through the node's physical interfaces.
* If you wish to use bridging, the default network can be removed by performing the following::

    mcvirt network delete default


Creating/Removing Networks
``````````````````````````

* Networks provide bridges between physical/bridge interfaces and virtual machines.
* To create a bridge network on the node, an additional network interface will need to be created on the node
* This will generally be placed in `/etc/network/interfaces`

The following example should help with creating this interface::

    auto vmbr0
    iface vmbr0 inet manual
      bridge_ports <Physical interface>
      bridge_stp off
      bridge_fd 0

Where `<Physical interface>` is the name of the interface that the bridge should be bridged with, e.g. 'eth0'


* To create a network on the node, perform the following as a superuser::

    mcvirt network create <Network name> --interface <Bridge interface>


* Assuming that there are not any VMs connected to a network, they can be removed using::

    mcvirt network delete <Network name>

Configure MCVirt
-----------------

* The first time MCVirt is run, it creates a configuration file for itself, found in **/var/lib/mcvirt/<Hostname>/config.json**.
* The volume group, in which VM data will be stored as logical volumes, must be setup using::

    mcvirt node --set-vm-vg <Volume Group>

* The cluster IP address must be configured if the node will be used in a cluster (See the `Cluster documentation <Cluster.rst>`_)::

    mcvirt node --set-ip-address <Cluster IP Address>

* In order for the MCVirt client to connect to the daemon, the hosts file at ``/etc/hosts`` must edited by changing the line::

    127.0.0.1    <hostname>

  to::

    <Cluster IP Address>    <hostname>

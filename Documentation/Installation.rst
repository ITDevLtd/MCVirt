============
Installation
============

Install Operating System
------------------------

* MCVirt is currently built to support Ubuntu 14.04 with native versions of dependencies.
* When installing the operating system, create the following logical volumes:
  * Root - Create a 50GB partition using ext4. This is used for the operating system, MCVirt configurations and ISO images
  * SWAP - leave the suggested SWAP volume unaltered

Building the package
--------------------

* Ensure the build dependencies are installed: ``dpkg, python-docutils``
* Clone the repository with: ``git clone https://github.com/ITDevLtd/MCVirt``
* From within the root of the working copy, run `build.sh <../build.sh>`_

Installing Package
------------------

To install the package, run::

$ sudo dpkg -i mcvirt_0.10_all.deb
$ sudo apt-get -f install

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

* The first time MCVirt is run, it creates a configuration file for itself, found in **/var/lib/mcvirt/config.json**.
* Set the volume group for the VMs to be stored in, within the configuration file.

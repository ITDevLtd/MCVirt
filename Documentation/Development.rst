===========
Development
===========

Coding Standards
----------------

The MCVirt code base follows the `python PEP 8 coding standards <https://www.python.org/dev/peps/pep-0008/>`_, with a line length limit of 100 characters.

All code changes must comply with this coding standard and are checked by continuous integration.

The pycodestyle code checker can be installed using::

  sudo pip install pycodestyle pylint flake8

Run the checks using::

  ./scripts/run_style_checks.sh

Automated Tests
---------------
There is a collection of unit tests for MCVirt, which can be run as follows::

  python /usr/lib/mcvirt/test/run_tests.py

Before runing the tests ensure that the ``mcvirt-ns`` service is running on all nodes in the cluster, and that ``mcvirtd`` is running on all nodes except the one the tests are being run on (since ``mcvirtd`` is started when the tests are run)

Manual Test Procedure
---------------------
This test procedure is designed to compliment the automated unit tests and should be performed prior to making a new release.

* Make sure the ``mcvirt-ns`` and ``mcvirtd`` daemons are started

* Create a VM called 'test-vm'

* Run ``mcvirt list`` and check that 'test-vm' is shown in the list, and that its state is 'STOPPED'

  * If the node is part of a cluster, run ``mcvirt list`` on another node in the cluster, and check that 'test-vm' is listed

* Start 'test-vm'. Run ``mcvirt list`` again and check that its state is now 'RUNNING'

  * Run ``mcvirt list`` on a remote node to check the state of 'test-vm' if the node is part of a cluster

* Try to delete 'test-vm' and check that an error is shown saying 'Can't delete a running VM'

* Stop 'test-vm', and try to delete it again. Check that it is no longer shown in the output of ``mcvirt list``

  * If the node is part of a cluster, confirm 'test-vm' has been deleted on a remote node too

* If the node is part of a cluster:

  * Make sure DRBD is enabled by running ``mcvirt drbd enable``

  * Create a new VM called 'cluster-vm', specifying the storage type as 'Drbd'

  * Start 'cluster-vm'

  * Test online migration of VMs by running ``mcvirt migrate --online --node <remote node>  cluster-vm``

  * Run ``mcvirt list`` on the local and remote nodes to check that 'cluster-vm' is now registered on the remote node


Suggested Development Environment
---------------------------------


Create virtual machine(s)
=========================

* Generally best to developer with 3 VMs
* Usually use 15GB HDD (20/25 might be better)
* 1 cpu core and 1GB RAM each
* Ensure that 'CPU feature passthrough' is enabled (or VXT-d flag  is enabled)
* Ensure that the VMs are on the same network, have access to the internet and are accessible from your PC (probably NAT network or similar)

* Generally develop using Ubuntu 18.04. (CI on build server runs against Ubuntu 14.04, 16.04, 18.04, Debian 8 and 9)
* Generally good to name the VMs something like 'mcvirt1, mcvirt2...'
* During installation: Use LVM and allocate around 5GB


Once installed, on each VM:

* Copy your SSH public key to root user on each VM, so that you can login automatically to root user.
* Update the VM name in /etc/hosts on the machine so that the names resolves to the private IP (not 127.0.0.1)

* Clone repo on local machine and rsync to each of the VMs
* Use ``https://github.com/ITDevLtd/MCVirt/blob/master/scripts/get_build_install.sh`` on each of the VMs::

    curl https://github.com/ITDevLtd/MCVirt/blob/add-installation-steps/scripts/get_build_install.sh | SOURCE_PATH=/path/to/rsynced/workingcopy bash -

* Update /etc/network/interfaces, so that:
  * Update ensX (or ethX) interface is set to manual
  * Add the following::

    auto vmbr0
    iface vmbr0 inet manual
     bridge_ports XXXX
     bridge_stp off
     bridge_fd 0

  * Replacing XXXX with the name of the interface ethX or ensX
* Reboot VM

Configuring
===========

* On each VM
  * Set IP address::

    mcvirt node --set-cluster-ip xxx.xxx.xxx.xxx

Replacing with the IP address of the VM


Create a cluster
================

* On a VM, run::

    mcvirt cluster get-connect-string

* On another node, run::

    mcvirt cluster add-node --connection-string <Output from other VM>

* Repeat this, running the first command on the third VM, ensuring that the second command is run on a machine that this has already been performed on. e.g. join 2 to 1 and then 3 to 1.


Create storage
==============

::

    mcvirt storage add --type Lvm --node mcvirt1 mcvirt1-vg --node mcvirt2 mcvirt2-vg --node mcvirt3 mcvirt3-vg local-vg-store

Create network
==============

::

    mcvirt network create --physical-interface vmbr0 local-net
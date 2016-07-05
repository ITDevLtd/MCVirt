===========
Development
===========

Coding Standards
----------------

The MCVirt code base follows the `python PEP 8 coding standards <https://www.python.org/dev/peps/pep-0008/>`_, with a line length limit of 100 characters.

All code changes must comply with this coding standard and are checked by continuous integration.

The PEP 8 code checker can be installed using::

  sudo apt-get install pep8

Run the checks using::

  pep8

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

  * Make sure DRBD is enabled by running ``mcvirt drbd --enable``

  * Create a new VM called 'cluster-vm', specifying the storage type as 'Drbd'

  * Start 'cluster-vm'

  * Test online migration of VMs by running ``mcvirt migrate --online --node <remote node>  cluster-vm``

  * Run ``mcvirt list`` on the local and remote nodes to check that 'cluster-vm' is now registered on the remote node

======
MCVirt - Managed Consistent Virtualisation
======

MCVirt ``(em-see-vert)`` - Command line virtual machine management utility.

Description
===========

MCVirt is a utility for managing virtual machines, supporting the following technologies:

* `Ubuntu 14.04 LTS <http://www.ubuntu.com/download/server>`_.
* `KVM virtualisation <http://www.linux-kvm.org/page/Main_Page>`_.
* Clustering with optional `DRBD <http://drbd.linbit.com/>`_ support.

MCVirt is implemented in Python, using the the `libvirt virtualisation library <http://libvirt.org>`_.

Getting started
===============

Installation
------------

MCVirt must currently be built from source into a deb package, using the build script. The package and dependencies can then be installed::

  $ ./build.sh
  $ sudo dpkg -i mcvirt_0.10_all.deb
  $ sudo apt-get -f install

See the `installation guide <Documentation/Installation.rst>`_ for other dependencies and system configuration.

Configuration
-------------

Configure the volume group that MCVirt will use to store virtual machine data.

Configure the MCVirt volume group::

  $ sudo mcvirt node --set-vm-vg <Volume Group>

See the `configuration guide <Documentation/Configuration.rst.rst>`_ for further node configuration steps.

Usage
-----

Create a VM::

  $ sudo mcvirt create --cpu-count 1 --memory 512 --disk-size 8000 test_vm

See the `create/remove VMs <Documentation/CreateRemoveVMs.rst>`_, `cluster <Documentation/Cluster.rst>`_, `permissions <Documentation/Permissions.rst>`_ and `modifying VMs <Documentation/ModifyingVMs.rst>`_ guides for further administrative instructions.

Start the VM::

  $ sudo mcvirt start test_vm

See the `controlling VMs guide <Documentation/ControllingVMs.rst>`_ for further user instructions.

Development
-----------

For information on developing on MCVirt, see the `development documentation <Documentation/Development.rst>`_.


Further information
-------------------

See the `guide index <Documentation/MCVirt.rst>`_ for a full list of manuals

For more information, please feel free to `contact us <http://www.itdev.co.uk/Contact/>`_


LICENSE
=======

MCVirt is licensed under GPL v2. For more information, please see `LICENSE <LICENSE>`_

COPYRIGHT
=========

.. |copy|   unicode:: U+000A9 .. COPYRIGHT SIGN

Copyright |copy| 2015 - `I.T. Dev Ltd <http://www.itdev.co.uk>`_


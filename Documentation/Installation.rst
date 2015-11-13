============
Installation
============

Install Operating System
------------------------

* MCVirt is currently built to support Ubuntu 14.04 with native versions of dependencies.
* When installing the operating system, create the following logical volumes:

  * Root - Create a 50GB partition using ext4. This is used for the operating system, MCVirt configurations and ISO images
  * SWAP - leave the suggested SWAP volume unaltered
* Virtual machine storage will be created as additional volumes in the volume group.

Building the package
--------------------

* Ensure the build dependencies are installed: ``dpkg, python-docutils``
* Clone the repository with: ``git clone https://github.com/ITDevLtd/MCVirt``
* From within the root of the working copy, run `build.sh <../build.sh>`_

Installing Package
------------------

To install the package, run::

$ sudo dpkg -i mcvirt_X.XX_all.deb
$ sudo apt-get -f install

Sudo Configuration
------------------

* MCVirt must always be run, either, using sudo or as root.
* MCVirt will handle user permissions based on the logged in user.
* If a user is to be able to use MCVirt and does not already have permission to run commands using sudo, the following sudoers rule can be used::

    example_username ALL=(ALL) /usr/bin/mcvirt
    %example_group ALL=(ALL) /usr/bin/mcvirt

Additionally, ``NOPASSWD:`` can be used to allow users to run MCVirt without having to re-enter their password::

    example_user ALL=(ALL) NOPASSWD: /usr/bin/mcvirt


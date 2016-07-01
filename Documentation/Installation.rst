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

MCVirt uses a customised version of `Pyro <https://pythonhosted.org/Pyro4/>`_, which can be installed by running::

$ git clone https://github.com/MatthewJohn/Pyro4
$ cd Pyro4
$ sudo pip install .

You may need to install `pip` by running `sudo apt-get install python-pip`.

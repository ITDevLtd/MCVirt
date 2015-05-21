
===========
Permissions
===========

All commands must be performed on the McVirt host, which can be accessed via SSH using LDAP credentials.


Managing users
==============

* In McVirt, 'users' are able to start/stop VMs
* To view the current permissions on a VM, including users and owners of a VM, run:

::

 mcvirt info <VM Name>


* To add a user to VM, perform the following:

::

 mcvirt permission --add-user <Username> <VM Name>

* To remove a user, perform the following:

::

 mcvirt permission --delete-user <Username> <VM Name>

Managing owners
===============

* VM owners have the same permissions as users, except they are also able to manage the users of the VM
* To add an owner to VM, perform the following:

::

 mcvirt permission --add-owner <Username> <VM Name>




* To remove an owner, perform the following:

::

 mcvirt permission --delete-owner <Username> <VM Name>



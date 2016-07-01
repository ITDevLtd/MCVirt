

Permissions
-----------

Superusers
````````````````````

* To run MCVirt commands as a superuser you must either:

  * Have your username included in the superusers section in the configuration file.

* Superusers can be added/removed using the following::

    mcvirt permission --add-superuser=<username>
    mcvirt permission --delete-superuser=<username>


Managing users
````````````````````````````

* To create a new user, perform the following as a superuser:

  ::

    mcvirt user create <new username>

  The password for the new user can be provided interactively, passed on the command line with ``--user-password <new password>``, or generated automatically with ``--generate-password``. The generated password will be displayed when the user is created.

* To remove a user, perform the following as a superuser:

  ::

    mcvirt user remove <user>

* To change your password, perform the following:

  ::

    mcvirt user change-password

  The new password can be provided interactively or on the command line with ``--new-password <new password>``. **Note:** Superusers can change the password of any other user by running ``mcvirt user change-password --target-user <other user>``.


* In MCVirt, 'users' are able to start/stop VMs
* To view the current permissions on a VM, including users and owners of a VM, run:

  ::

    mcvirt info <VM Name>



* To add a user to VM, perform the following:

  ::

    mcvirt permission --add-user <Username> <VM Name>



* To remove a user, perform the following:

  ::

    mcvirt permission --delete-user <Username> <VM Name>


* **Owners** of a VM are able to manage the **users** of a VM.



Managing owners
`````````````````````````````


* VM owners have the same permissions as users, except they are also able to manage the users of the VM

* To add an owner to VM, perform the following:

  ::

    mcvirt permission --add-owner <Username> <VM Name>



* To remove an owner, perform the following:

  ::

    mcvirt permission --delete-owner <Username> <VM Name>



* Only superusers are able to manage the **owners** of a VM.
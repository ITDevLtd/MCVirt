

Permissions
-----------

Superusers
````````````````````

* To run MCVirt commands as a superuser you must either:

  * Have your username included in the superusers section in the configuration file.
    **Note:** You will still have to run MCVirt commands using sudo, as MCVirt determines the permissions based on the username of the user that has run sudo.
    
    Sudo can be configured to allow you to run MCVirt using sudo with no password. To do this you can run ``visudo`` as root and add the following line: ``<Your username here> ALL=(ALL) NOPASSWD: /usr/bin/mcvirt``
  
  * Be logged in as root.

* Superusers can be added/removed using the following::

    sudo mcvirt permission --add-superuser=<username>
    sudo mcvirt permission --delete-superuser=<username>


Managing users
````````````````````````````


* In MCVirt, 'users' are able to start/stop VMs
* To view the current permissions on a VM, including users and owners of a VM, run:

  ::
    
    sudo mcvirt info <VM Name>
    


* To add a user to VM, perform the following:

  ::
    
    sudo mcvirt permission --add-user <Username> <VM Name>
    


* To remove a user, perform the following:

  ::
    
    sudo mcvirt permission --delete-user <Username> <VM Name>
    

* **Owners** of a VM are able to manage the **users** of a VM.



Managing owners
`````````````````````````````


* VM owners have the same permissions as users, except they are also able to manage the users of the VM

* To add an owner to VM, perform the following:

  ::
    
    sudo mcvirt permission --add-owner <Username> <VM Name>
    


* To remove an owner, perform the following:

  ::
    
    sudo mcvirt permission --delete-owner <Username> <VM Name>
    


* Only superusers are able to manage the **owners** of a VM.


Permissions
-----------


* All commands must be performed on the MCVirt host, which can be accessed via SSH using LDAP credentials.



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
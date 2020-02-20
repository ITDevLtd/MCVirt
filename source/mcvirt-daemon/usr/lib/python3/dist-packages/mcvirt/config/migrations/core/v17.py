# Copyright (c) 2018 - Matt Comben
#
# This file is part of MCVirt.
#
# MCVirt is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# MCVirt is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/>

import hashlib
import json

from mcvirt.constants import DirectoryLocation


def migrate(config_obj, config):
    """Migrate v17"""
    # Little bit crazy, but need to load VM configs from
    # old VM config files (since there won't be any supporting
    # classes/methods to help) and move contents into MCVirt config
    new_vm_config_dict = {}
    for vm_name in config['virtual_machines']:
        # Generate ID for VM
        name_checksum = hashlib.sha512(vm_name).hexdigest()
        date_checksum = hashlib.sha512('0').hexdigest()
        vm_id = 'vm-%s-%s' % (name_checksum[0:18], date_checksum[0:22])

        # Obtain VM config
        vm_config_fh = open('%s/vm/%s/config.json' % (
            DirectoryLocation.NODE_STORAGE_DIR, vm_name), 'r')
        vm_config = json.loads(vm_config_fh.read())
        vm_config_fh.close()

        # Add config to the new VM config
        new_vm_config_dict[vm_id] = vm_config

        # Add VM name to the VM config
        new_vm_config_dict[vm_id]['name'] = vm_name

        # TODO GIT RM ORIGINAL CONFIG

    config['virtual_machines'] = new_vm_config_dict

    # Convert blank DRBD secret to null value and enabled int to a boolean
    if config['drbd']['secret'] == '':
        config['drbd']['secret'] = None
    config['drbd']['enabled'] = bool(config['drbd']['enabled'])

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


def migrate(config_obj, config):
    """Migrate v18"""
    # Migrate hard drive objects from virtual machines to
    # seperate hard drive objects
    hard_drive_dict = {}
    for vm_id, vm_config in config['virtual_machines'].items():
        for hdd_attachment_id, vm_hdd_config in vm_config['hard_disks'].items():
            # Get base volume name
            base_volume_name = (
                vm_hdd_config['custom_disk_name']
                if 'custom_disk_name' in vm_hdd_config else
                'mcvirt_vm-%s-disk-%s' % (vm_config['name'], hdd_attachment_id))

            # Generate ID for hard_drive
            name_checksum = hashlib.sha512(base_volume_name).hexdigest()
            date_checksum = hashlib.sha512('0').hexdigest()
            hdd_id = 'hd-%s-%s' % (name_checksum[0:18], date_checksum[0:22])

            hard_drive_dict[hdd_id] = {
                'base_volume_name': base_volume_name
            }

            if 'custom_disk_name' in vm_hdd_config:
                del vm_hdd_config['custom_disk_name']

            hard_drive_dict[hdd_id]['storage_backend'] = vm_hdd_config['storage_backend']
            del vm_hdd_config['storage_backend']
            hard_drive_dict[hdd_id]['driver'] = vm_hdd_config['driver']
            del vm_hdd_config['driver']

            # Obtain configs from original VM hdd config
            if 'drbd_minor' in vm_hdd_config:
                hard_drive_dict[hdd_id]['drbd_minor'] = vm_hdd_config['drbd_minor']
                del vm_hdd_config['drbd_minor']
            if 'drbd_port' in vm_hdd_config:
                hard_drive_dict[hdd_id]['drbd_port'] = vm_hdd_config['drbd_port']
                del vm_hdd_config['drbd_port']
            if 'sync_state' in vm_hdd_config:
                hard_drive_dict[hdd_id]['sync_state'] = vm_hdd_config['sync_state']
                del vm_hdd_config['sync_state']

            hard_drive_dict[hdd_id]['nodes'] = vm_config['available_nodes']

            vm_hdd_config['hard_drive_id'] = hdd_id

            hard_drive_dict[hdd_id]['storage_type'] = vm_config['storage_type']

        # Remove old storage type config from VM
        del vm_config['storage_type']
        vm_config['hard_drives'] = vm_config['hard_disks']
        del vm_config['hard_disks']

    # Add new hard drive config to global config
    config['hard_drives'] = hard_drive_dict

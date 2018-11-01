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


def migrate(config_obj, config):
    """Migrate v18"""
    # Update permissions, adding new MODIFY_HARD_DRIVE permission
    # where the MODIFY_VM permission was previously assigned
    for group_id in config['groups']:
        if 'MODIFY_VM' in config['groups'][group_id]['permissions']:
            config['groups'][group_id]['permissions'].append('MODIFY_HARD_DRIVE')

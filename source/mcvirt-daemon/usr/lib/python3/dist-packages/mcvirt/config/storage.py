# Copyright (c) 2014 - I.T. Dev Ltd
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

from mcvirt.config.base_subconfig import BaseSubconfig
import mcvirt.config.migrations.storage as migrations


class Storage(BaseSubconfig):
    """Provides operations to obtain and set the MCVirt configuration for a VM."""

    SUBTREE_ARRAY = ['storage_backends']

    def __init__(self, storage_obj):
        """Sets member variables."""
        self.storage_obj = storage_obj
        super(Storage, self).__init__()

    def _get_config_key(self):
        """Get the key for the config."""
        return self.storage_obj.id_

    @staticmethod
    def create(storage_backend_id, config):
        """Add a storage backend config."""

        # Write the configuration to disk
        Storage._add_config(
            storage_backend_id, config,
            'Add storage backend config: %s' % storage_backend_id)

    def _upgrade(self, config):
        """Perform an upgrade of the configuration file."""
        pass

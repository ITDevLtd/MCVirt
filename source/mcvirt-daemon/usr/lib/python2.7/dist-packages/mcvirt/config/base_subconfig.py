"""Provide base class for configuration files"""

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

import json
import os
import stat
import pwd
import shutil

from mcvirt.config.mcvirt import MCVirtConfig


class BaseSubconfig(MCVirtConfig):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    SUBTREE_ARRAY = []

    def _get_config_key(self):
        """Get the key for the config, default to no key, which will be skipped"""
        return None

    def get_config(self):
        """Load the VM configuration from disk and returns the parsed JSON."""
        # Get config from parent, which should be the whole config
        parent_config = super(BaseSubconfig, self).get_config()

        # Traverse the parent config, to get the sub config
        subconfig = parent_config
        for key_itx in self.SUBTREE_ARRAY + [self._get_config_key()]:
            subconfig = subconfig[key_itx]

        # Return the sub config
        return subconfig

    def update_config(self, callback_function, reason=''):
        """Write a provided configuration back to the configuration file."""
        def update_sub_config(config):
            """Update the subconfig"""
            # Traverse the parent config to get the subconfig
            subconfig = config
            for key_itx in self.SUBTREE_ARRAY + [self._get_config_key()]:
                if key_itx:
                    subconfig = subconfig[key_itx]

            # Call callback function with subconfig
            callback_function(subconfig)

        # Call parent update_config method, overriding the callback
        # method
        super(BaseSubconfig, self).update_config(update_sub_config, reason)

    @classmethod
    def _add_config(cls, id_, config, reason):
        """Add config to parent config"""
        def add_config_to_parent_config(mcvirt_config):
            """Add subconfig to parent config"""
            # Traverse down parent config to get parent dict
            subconfig = mcvirt_config
            for key_itx in cls.SUBTREE_ARRAY:
                subconfig = subconfig[key_itx]

            # Add subconfig, using key index
            subconfig[id_] = config

        # Update MCVirt config with the new config
        MCVirtConfig().update_config(
            add_config_to_parent_config,
            reason)


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

from mcvirt.config.core import Core


class BaseSubconfig(Core):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    SUBTREE_ARRAY = []

    def __init__(self):
        """Perform upgrade"""
        # If performing an upgrade has been specified, do so
        self.upgrade()

    def _get_config_key(self):
        """Get the key for the config, default to no key, which will be skipped"""
        return None

    @classmethod
    def get_global_config(cls):
        """Obtain entire config for this object type"""
        # Get config from parent, which should be the whole config
        parent_config = Core().get_config()

        # Traverse the parent config, to get the sub config
        subconfig = parent_config
        for key_itx in cls.SUBTREE_ARRAY:
            subconfig = subconfig[key_itx]

        # Return the sub config
        return subconfig

    def get_config(self):
        """Get the config for the object."""
        # Return the object ID value from the config dict
        return self.__class__.get_global_config()[self._get_config_key()]

    def update_config(self, callback_function, reason=''):
        """Write a provided configuration back to the configuration file."""
        def update_sub_config(config):
            """Update the subconfig"""
            # Traverse the parent config to get the subconfig
            subconfig = config
            for key_itx in self.__class__.SUBTREE_ARRAY + [self._get_config_key()]:
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
        Core().update_config(
            add_config_to_parent_config,
            reason)

    def delete(self):
        """Remove config from parent config"""
        config_key = self._get_config_key()

        def remove_from_parent(config):
            """Remove item from parent config"""
            # Traverse down parent config to get parent dict
            subconfig = config
            for key_itx in self.__class__.SUBTREE_ARRAY:
                subconfig = subconfig[key_itx]
            del subconfig[config_key]
        Core().update_config(
            remove_from_parent,
            'Removing object %s' % config_key)

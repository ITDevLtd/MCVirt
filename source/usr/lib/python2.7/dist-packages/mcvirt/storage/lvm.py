# Copyright (c) 2018 - I.T. Dev Ltd
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


from mcvirt.storage.base import Base
from mcvirt.exceptions import InvalidStorageConfiguration, InvalidNodesException


class Lvm(Base):
    """Storage backend for LVM based storage"""

    @staticmethod
    def validate_config(node, cluster, config):
        """Validate config"""
        Base.validate_config(cluster, config)

        # Ensure that all nodes specified are valid

        # Check local node, if it has been defined
        if cluster.get_local_hostname() in config['nodes']:
            # Get overriden location, if defined
            if config['nodes'][cluster.get_local_hostname()]['location']:
                vg_name = config['nodes'][cluster.get_local_hostname()]['location']

            # Else, if defined, use the default location
            elif config['location']:
                vg_name = config['location']

            # Otherwise, if node if defined and no locaftion is defined,
            # raise an error
            else:
                raise InvalidStorageConfiguration(
                    'No node-specific volume group specified for node: %s' %
                    cluster.get_local_hostname()
                )
            if not node.volume_group_exists(vg_name):
                raise InvalidStorageConfiguration(
                    'Volume group %s does not exist on node: %s' %
                    (vg_name, cluster.get_local_hostname())
                )

        def remote_command(remote_object):
            node = remote_object.get_connection('node')
            if (remote_object.name in config['nodes'] and
                    config['nodes'][remote_object.name]['location']):
                vg_name = config['nodes'][remote_object.name]['location']
            elif config['location']:
                vg_name = config['location']
            else:
                raise InvalidStorageConfiguration(
                    'No node-specific volume group specified for node: %s' % remote_object.name
                )
            if not node.volume_group_exists(vg_name):
                raise InvalidStorageConfiguration(
                    'Volume group %s does not exist on node: %s' % (vg_name, remote_object.name)
                )
        cluster.run_remote_command(remote_command, nodes=config['nodes'])

    def get_location(self, node=None):
        """Return volume group name for the local host"""
        if node is None:
            node = self._get_registered_object('cluster').get_local_hostname()
        storage_config = self.get_config()
        if node in storage_config['nodes'] and 'location' in storage_config['nodes'][node]:
            return storage_config['nodes']['location']
        elif storage_config['location']:
            return storage_config['location']
        else:
            raise InvalidNodesException('Storage %s not defined on %s' % (self.name, node))

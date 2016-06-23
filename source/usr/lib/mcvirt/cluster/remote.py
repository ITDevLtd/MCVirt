"""Provide interface for RPC to cluster nodes"""

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


from mcvirt.client.rpc import Connection


class Node(Connection):
    """A class to perform remote commands on MCVirt nodes"""

    def __init__(self, name, node_config):
        """Set member variables"""
        self.name = name
        self.ip_address = node_config['ip_address'] if 'ip_address' in node_config else None
        super(Node, self).__init__(username=node_config['username'],
                                   password=node_config['password'],
                                   host=self.name)

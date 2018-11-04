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


def migrate(db_inst):
    """Initial schema for database"""

    # Create table for storing schema version and insert row for version
    db_inst.cursor.execute("""CREATE TABLE mcvirt_schema(version INT)""")
    db_inst.cursor.execute("""INSERT INTO mcvirt_schema(version) VALUES(0)""")

    db_inst.cursor.execute("""CREATE TABLE stats(
                                  device_type INT, device_id VARCHAR,
                                  stat_type INT, stat_value REAL,
                                  stat_date INT
                              )""")

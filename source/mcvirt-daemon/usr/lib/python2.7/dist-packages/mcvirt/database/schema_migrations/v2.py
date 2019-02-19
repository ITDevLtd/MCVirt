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
    # Create replacement table for stats
    curs = db_inst.cursor
    curs.execute("""CREATE TABLE stats_new(
                    device_type INT, device_id VARCHAR,
                    stat_type INT, stat_value BLOB,
                    stat_date INT
                    )""")
    sel_curs = db_inst.cursor
    sel_curs.execute('SELECT * FROM stats')
    for row in sel_curs:
        curs.execute("""
            INSERT INTO
            stats_new(
                device_type, device_id, stat_type, stat_value, stat_date
            )
            VALUES (?, ?, ?, ?, ?)""", row)
    curs.execute('DROP TABLE stats')
    curs.execute('ALTER TABLE stats_new RENAME TO stats')
    curs.commit()

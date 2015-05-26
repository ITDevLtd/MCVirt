#!/usr/bin/python
# Copyright (c) 2015 - I.T. Dev Ltd
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
"""
Script to build the man page for MCVirt.
"""
import os

from docutils.core import publish_doctree, publish_from_doctree
from docutils.nodes import Text, version
from docutils.writers import manpage

MANPAGE = 'manpage.rst'
VERSION = 'VERSION'
OUT_DIR = 'man1'


def get_version():
    """Get the version from the version
    file.
    """
    with open(VERSION, 'r') as v_file:
        return v_file.read()


if __name__ == "__main__":
    with open(MANPAGE, 'r') as man_file:
        doctree = publish_doctree(man_file.read())
    for field in doctree.traverse(condition=version):
        field += Text(' %s' % get_version())
    # Create the man1 dir if not exists
    if not os.path.exists(OUT_DIR):
        os.mkdir(OUT_DIR)
    output = publish_from_doctree(doctree, writer=manpage.Writer())
    with open(os.path.join(OUT_DIR, 'mcvirt.1'), 'w') as out_file:
        out_file.write(output)

#!/bin/bash

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

which pep8 > /dev/null 2>&1

if [ "$?" != "0" ]
then
  sudo apt-get install pep8 --assume-yes
fi

pep8 --max-line-length=100 ./ ./source/usr/bin/mcvirt ./source/usr/bin/mcvirt_sudo

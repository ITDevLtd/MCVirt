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

import getpass
import subprocess
import sys

from mcvirt.exceptions import MCVirtCommandException, PasswordsDoNotMatchException


class System(object):

    @staticmethod
    def runCommand(command_args, raise_exception_on_failure=True, cwd=None):
        """Runs system command, throwing an exception if the exit code is not 0"""
        command_process = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd)
        if (command_process.wait() and raise_exception_on_failure):
            raise MCVirtCommandException(
                "Command: %s\nExit code: %s\nOutput:\n%s" %
                (' '.join(command_args),
                 command_process.returncode,
                 command_process.stdout.read() +
                 command_process.stderr.read()))
        return (
            command_process.returncode,
            command_process.stdout.read(),
            command_process.stderr.read())

    @staticmethod
    def getUserInput(display_text, password=False):
        """Prompts the user for input"""
        if (password):
            return getpass.getpass(display_text)
        else:
            sys.stdout.write(display_text)
            return sys.stdin.readline()

    @staticmethod
    def getNewPassword():
        """Prompts the user for a new password, throwing an exception is the password is not
        repeated correctly
        """
        new_password = System.getUserInput("New password: ", password=True)
        repeat_password = System.getUserInput("New password (repeat): ", password=True)
        if new_password != repeat_password:
            raise PasswordsDoNotMatchException('The two passwords do not match')

        return new_password

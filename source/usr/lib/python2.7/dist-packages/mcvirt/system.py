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

from mcvirt.exceptions import (MCVirtCommandException,
                               PasswordsDoNotMatchException,
                               DDCommandError)
from mcvirt.syslogger import Syslogger


class System(object):

    # Constant used to pass to perform_dd, which specifies will wipe the destination
    WIPE = object()

    @staticmethod
    def runCommand(command_args, raise_exception_on_failure=True, cwd=None):
        """Runs system command, throwing an exception if the exit code is not 0"""
        command_process = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd)
        Syslogger.logger().debug('Started system command: %s' % ', '.join(command_args))
        rc = command_process.wait()
        stdout = command_process.stdout.read()
        stderr = command_process.stderr.read()
        if rc and raise_exception_on_failure:
            Syslogger.logger().error("Failed system command: %s\nRC: %s\nStdout: %s\nStderr: %s" %
                                     (', '.join(command_args), rc, stdout, stderr))
            raise MCVirtCommandException(('External command failure. '
                                          'See MCVirt log for more information'))

        Syslogger.logger().debug("Successful system command: %s\nRC: %s\nStdout: %s\nStderr: %s" %
                                 (', '.join(command_args), rc, stdout, stderr))
        return (rc, stdout, stderr)

    @staticmethod
    def getUserInput(display_text, password=False):
        """Prompt the user for input"""
        if password:
            return getpass.getpass(display_text)
        else:
            sys.stdout.write(display_text)
            return sys.stdin.readline()

    @staticmethod
    def getNewPassword():
        """Prompt the user for a new password, throwing an exception is the password is not
        repeated correctly
        """
        new_password = System.getUserInput("New password: ", password=True)
        repeat_password = System.getUserInput("New password (repeat): ", password=True)
        if new_password != repeat_password:
            raise PasswordsDoNotMatchException('The two passwords do not match')

        return new_password

    @staticmethod
    def is_running_systemd():
        """Determine if machine is running systemd"""
        exit_code, _, _ = System.runCommand(['pidof', 'systemd'], raise_exception_on_failure=False)
        return exit_code == 0

    @staticmethod
    def perform_dd(source, destination, size):
        """Perform a 'dd' system command to replicate storage
           block-by-block"""
        # If wipe is specified, zero the destination
        if source is System.WIPE:
            source = '/dev/zero'

        # Compile command arguments
        command_args = ['dd', 'if=%s' % source, 'of=%s' % destination,
                        'bs=1M', 'conv=fsync', 'oflag=direct',
                        'count=%s' % size]

        try:
            # Perform the dd command
            System.runCommand(command_args)

        except MCVirtCommandException, e:
            raise DDCommandError(
                "Error whilst running dd:\n" + str(e)
            )

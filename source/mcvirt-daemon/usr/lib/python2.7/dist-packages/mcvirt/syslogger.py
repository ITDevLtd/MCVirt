# Copyright (c) 2016 - I.T. Dev Ltd
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

import logging
import os

from mcvirt.constants import DirectoryLocation


class Syslogger(object):
    """Provide interface for logging to log file"""

    LOGGER_INSTANCE = None

    @staticmethod
    def logger():
        """Obtain logger instance if not already create, else return cached object"""
        if Syslogger.LOGGER_INSTANCE is None:
            logger = logging.getLogger('mcvirtd')
            logger.setLevel(getattr(logging, Syslogger.get_log_level(), 30))
            Syslogger.LOGGER_INSTANCE = logger

            Syslogger.HANDLER = logging.FileHandler(DirectoryLocation.LOG_FILE)
            Syslogger.HANDLER.setLevel(getattr(logging, Syslogger.get_log_level(), 30))
            formatter = logging.Formatter(('%(asctime)s %(name)-12s %(pathname)s'
                                           ' %(lineno)d: %(funcName)s %(levelname)-8s'
                                           ' %(message)s'))
            Syslogger.HANDLER.setFormatter(formatter)
            Syslogger.LOGGER_INSTANCE.addHandler(Syslogger.HANDLER)

        return Syslogger.LOGGER_INSTANCE

    @staticmethod
    def get_log_level():
        """Return the log level, set either by environmental variable
        or configuration in MCVirt config
        """
        from mcvirt.config.mcvirt import MCVirt as MCVirtConfig
        if 'MCVIRT_DEBUG' in os.environ:
            return os.environ['MCVIRT_DEBUG'].upper()
        else:
            return MCVirtConfig().get_config()['log_level'].upper()

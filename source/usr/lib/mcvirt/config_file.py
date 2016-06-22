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

import json
import os
import stat
import pwd

from mcvirt.utils import get_hostname
from mcvirt.system import System
from mcvirt.constants import Constants


class ConfigFile(object):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    CURRENT_VERSION = 4
    GIT = '/usr/bin/git'

    def __init__(self):
        """Sets member variables and obtains libvirt domain object"""
        raise NotImplementedError

    @staticmethod
    def getConfigPath(vm_name):
        """Provides the path of the VM-spefic configuration file"""
        raise NotImplementedError

    def getConfig(self):
        """Loads the VM configuration from disk and returns the parsed JSON"""
        config_file = open(self.config_file, 'r')
        config = json.loads(config_file.read())
        config_file.close()

        return config

    def updateConfig(self, callback_function, reason=''):
        """Writes a provided configuration back to the configuration file"""
        config = self.getConfig()
        callback_function(config)
        ConfigFile._writeJSON(config, self.config_file)
        self.config = config
        self.gitAdd(reason)
        self.setConfigPermissions()

    def getPermissionConfig(self):
        config = self.getConfig()
        return config['permissions']

    @staticmethod
    def _writeJSON(data, file_name):
        """Parses and writes the JSON VM config file"""
        json_data = json.dumps(data, indent=2, separators=(',', ': '))

        # Open the config file and write to contents
        config_file = open(file_name, 'w')
        config_file.write(json_data)
        config_file.close()

        # Check file permissions, only giving read/write access to root
        os.chmod(file_name, stat.S_IWUSR | stat.S_IRUSR)
        os.chown(file_name, 0, 0)

    @staticmethod
    def create(self):
        """Creates a basic VM configuration for new VMs"""
        raise NotImplementedError

    def setConfigPermissions(self):
        """Sets file permissions for config directories"""
        def setPermission(path, directory=True, owner=0):
            permission_mode = stat.S_IRUSR
            if directory:
                permission_mode = permission_mode | stat.S_IWUSR | stat.S_IXUSR

            if (directory and os.path.isdir(path) or
                    not directory and os.path.exists(path)):
                os.chown(path, owner, 0)
                os.chmod(path, permission_mode)

        # Set permissions on git directory
        for directory in os.listdir(Constants.BASE_STORAGE_DIR):
            path = os.path.join(Constants.BASE_STORAGE_DIR, directory)
            if (os.path.isdir(path)):
                if (directory == '.git'):
                    setPermission(path, directory=True)
                else:
                    setPermission(os.path.join(path, 'vm'), directory=True)
                    setPermission(os.path.join(path, 'config.json'), directory=False)

        # Set permission for base directory, node directory and ISO directory
        for directory in [Constants.BASE_STORAGE_DIR, Constants.NODE_STORAGE_DIR,
                          Constants.ISO_STORAGE_DIR]:
            setPermission(directory, directory=True,
                          owner=pwd.getpwnam('libvirt-qemu').pw_uid)

    def _upgrade(self, config):
        """Updates the configuration file"""
        raise NotImplementedError

    def upgrade(self):
        """Performs an upgrade of the config file"""
        # Check the version of the configuration file
        current_version = self._getVersion()
        if (current_version < self.CURRENT_VERSION):
            def upgradeConfig(config):
                # Perform the configuration sub-class specific upgrade
                # tasks
                self._upgrade(config)
                # Update the version number of the configuration file to
                # the current version
                config['version'] = self.CURRENT_VERSION
            self.updateConfig(
                upgradeConfig,
                'Updated configuration file \'%s\' from version \'%s\' to \'%s\'' %
                (self.config_file,
                 current_version,
                 self.CURRENT_VERSION))

    def _getVersion(self):
        """Returns the version number of the configuration file"""
        config = self.getConfig()
        if ('version' in config.keys()):
            return config['version']
        else:
            return 0

    def gitAdd(self, message=''):
        """Commits changes to an added or modified configuration file"""
        from auth.session import Session
        if (self._checkGitRepo()):
            message += "\nUser: %s\nNode: %s" % (Session.getCurrentUserObject().getUsername(), get_hostname())
            try:
                System.runCommand([self.GIT, 'add', self.config_file], cwd=Constants.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'commit',
                                   '-m',
                                   message,
                                   self.config_file],
                                  cwd=Constants.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=Constants.BASE_STORAGE_DIR)
            except:
                pass

    def gitRemove(self, message=''):
        """Removes and commits a configuration file"""
        from auth.session import Session
        if self._checkGitRepo():
            message += "\nUser: %s\nNode: %s" % (Session.getCurrentUserObject().getUsername(),
                                                 get_hostname())
            try:
                System.runCommand([self.GIT,
                                   'rm',
                                   '--cached',
                                   self.config_file],
                                  cwd=Constants.BASE_STORAGE_DIR)
                System.runCommand([self.GIT, 'commit', '-m', message], cwd=Constants.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=Constants.BASE_STORAGE_DIR)
            except:
                pass

    def _checkGitRepo(self):
        """Clones the configuration repo, if necessary, and updates the repo"""
        from mcvirt_config import MCVirtConfig

        # Only attempt to create a git repository if the git
        # URL has been set in the MCVirt configuration
        mcvirt_config = MCVirtConfig().getConfig()
        if mcvirt_config['git']['repo_domain'] == '':
            return False

        # Attempt to create git object, if it does not already exist
        if not os.path.isdir(Constants.BASE_STORAGE_DIR + '/.git'):

            # Initialise git repository
            System.runCommand([self.GIT, 'init'], cwd=Constants.BASE_STORAGE_DIR)

            # Set git name and email address
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               Constants.BASE_STORAGE_DIR +
                               '/.git/config', 'user.name', mcvirt_config['git']['commit_name']])
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               Constants.BASE_STORAGE_DIR +
                               '/.git/config', 'user.email', mcvirt_config['git']['commit_email']])

            # Create git-credentials store
            System.runCommand([self.GIT,
                               'config',
                               '--file=%s' % Constants.BASE_STORAGE_DIR + '/.git/config',
                               'credential.helper',
                               'store --file /root/.git-credentials'])
            git_credentials = '%s://%s:%s@%s' % (mcvirt_config['git']['repo_protocol'],
                                                 mcvirt_config['git']['username'],
                                                 mcvirt_config['git']['password'],
                                                 mcvirt_config['git']['repo_domain'])
            fh = open('/root/.git-credentials', 'w')
            fh.write(git_credentials)
            fh.close()

            # Add the git remote
            System.runCommand(
                [
                    self.GIT,
                    'remote',
                    'add',
                    'origin',
                    mcvirt_config['git']['repo_protocol'] +
                    '://' +
                    mcvirt_config['git']['repo_domain'] +
                    '/' +
                    mcvirt_config['git']['repo_path']],
                cwd=Constants.BASE_STORAGE_DIR)

            # Update the repo
            System.runCommand([self.GIT, 'fetch'], cwd=Constants.BASE_STORAGE_DIR)
            System.runCommand([self.GIT, 'checkout', 'master'], cwd=Constants.BASE_STORAGE_DIR)
            System.runCommand([self.GIT,
                               'branch',
                               '--set-upstream-to',
                               'origin/master',
                               'master'],
                              cwd=Constants.BASE_STORAGE_DIR)

            # Perform an initial commit of the configuration file
            self.gitAdd('Initial commit of configuration file.')

        else:
            # Update repository
            System.runCommand([self.GIT,
                               'pull'],
                              raise_exception_on_failure=False,
                              cwd=Constants.BASE_STORAGE_DIR)

        return True

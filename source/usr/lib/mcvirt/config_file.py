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


class ConfigFile():
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    CURRENT_VERSION = 1
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

    def getPermissionConfig(self):
        config = self.getConfig()
        return config['permissions']

    @staticmethod
    def _writeJSON(data, file_name):
        """Parses and writes the JSON VM config file"""
        import pwd
        import stat
        json_data = json.dumps(data, indent=2, separators=(',', ': '))

        # Open the config file and write to contents
        config_file = open(file_name, 'w')
        config_file.write(json_data)
        config_file.close()

        # Check file permissions, only giving read/write access to libvirt-qemu/root
        os.chmod(file_name, stat.S_IWUSR | stat.S_IRUSR)
        os.chown(file_name, pwd.getpwnam('libvirt-qemu').pw_uid, 0)

    @staticmethod
    def create(self):
        """Creates a basic VM configuration for new VMs"""
        raise NotImplementedError

    def _upgrade(self, mcvirt_instance, config):
        """Updates the configuration file"""
        raise NotImplementedError

    def upgrade(self, mcvirt_instance):
        """Performs an upgrade of the config file"""
        # Check the version of the configuration file
        current_version = self._getVersion()
        if (current_version < self.CURRENT_VERSION):
            def upgradeConfig(config):
                # Perform the configuration sub-class specific upgrade
                # tasks
                self._upgrade(mcvirt_instance, config)
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
        from system import System
        from mcvirt import MCVirt
        from auth import Auth
        from cluster.cluster import Cluster
        if (self._checkGitRepo()):
            message += "\nUser: %s\nNode: %s" % (Auth.getUsername(), Cluster.getHostname())
            try:
                System.runCommand([self.GIT, 'add', self.config_file], cwd=MCVirt.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'commit',
                                   '-m',
                                   message,
                                   self.config_file],
                                  cwd=MCVirt.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=MCVirt.BASE_STORAGE_DIR)
            except:
                pass

    def gitRemove(self, message=''):
        """Removes and commits a configuration file"""
        from system import System
        from mcvirt import MCVirt
        from auth import Auth
        from cluster.cluster import Cluster
        if (self._checkGitRepo()):
            message += "\nUser: %s\nNode: %s" % (Auth.getUsername(), Cluster.getHostname())
            try:
                System.runCommand([self.GIT,
                                   'rm',
                                   '--cached',
                                   self.config_file],
                                  cwd=MCVirt.BASE_STORAGE_DIR)
                System.runCommand([self.GIT, 'commit', '-m', message], cwd=MCVirt.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=MCVirt.BASE_STORAGE_DIR)
            except:
                pass

    def _checkGitRepo(self):
        """Clones the configuration repo, if necessary, and updates the repo"""
        from mcvirt import MCVirt
        from mcvirt_config import MCVirtConfig
        from system import System

        # Only attempt to create a git repository if the git
        # URL has been set in the MCVirt configuration
        mcvirt_config = MCVirtConfig().getConfig()
        if (mcvirt_config['git']['repo_domain'] == ''):
            return False

        # Attempt to create git object, if it does not already exist
        if (not os.path.isdir(MCVirt.BASE_STORAGE_DIR + '/.git')):

            # Initialise git repository
            System.runCommand([self.GIT, 'init'], cwd=MCVirt.BASE_STORAGE_DIR)

            # Set git name and email address
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               MCVirt.BASE_STORAGE_DIR +
                               '/.git/config', 'user.name', mcvirt_config['git']['commit_name']])
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               MCVirt.BASE_STORAGE_DIR +
                               '/.git/config', 'user.email', mcvirt_config['git']['commit_email']])

            # Create git-credentials store
            System.runCommand([self.GIT,
                               'config',
                               '--file=%s' % MCVirt.BASE_STORAGE_DIR + '/.git/config',
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
                cwd=MCVirt.BASE_STORAGE_DIR)

            # Update the repo
            System.runCommand([self.GIT, 'fetch'], cwd=MCVirt.BASE_STORAGE_DIR)
            System.runCommand([self.GIT, 'checkout', 'master'], cwd=MCVirt.BASE_STORAGE_DIR)
            System.runCommand([self.GIT,
                               'branch',
                               '--set-upstream-to',
                               'origin/master',
                               'master'],
                              cwd=MCVirt.BASE_STORAGE_DIR)

            # Perform an initial commit of the configuration file
            self.gitAdd('Initial commit of configuration file.')

        else:
            # Update repository
            System.runCommand([self.GIT,
                               'pull'],
                              raise_exception_on_failure=False,
                              cwd=MCVirt.BASE_STORAGE_DIR)

        return True

"""Provide base class for configuration files"""

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
import shutil

from mcvirt.utils import get_hostname
from mcvirt.system import System
from mcvirt.constants import DirectoryLocation
from mcvirt.rpc.pyro_object import PyroObject
from mcvirt.rpc.expose_method import Expose
from mcvirt.auth.permissions import PERMISSIONS
from mcvirt.exceptions import UserDoesNotExistException


class ConfigFile(PyroObject):
    """Provides operations to obtain and set the MCVirt configuration for a VM"""

    CURRENT_VERSION = 17
    GIT = '/usr/bin/git'

    def __init__(self):
        """Set member variables and obtains libvirt domain object"""
        raise NotImplementedError

    @staticmethod
    def get_config_path(vm_name):
        """Provide the path of the VM-specific configuration file"""
        raise NotImplementedError

    def get_config(self):
        """Load the VM configuration from disk and returns the parsed JSON."""
        config_file = open(self.config_file, 'r')
        config = json.loads(config_file.read())
        config_file.close()

        return config

    @Expose(locking=True)
    def get_config_remote(self):
        """Provide an exposed method for reading MCVirt configuration"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SUPERUSER)
        return self.get_config()

    @Expose(locking=True)
    def manual_update_config(self, config, reason=''):
        """Provide an exposed method for updating the config"""
        self._get_registered_object('auth').assert_permission(PERMISSIONS.SUPERUSER)
        ConfigFile._writeJSON(config, self.config_file)
        self.config = config
        self.gitAdd(reason)
        self.setConfigPermissions()

    def update_config(self, callback_function, reason=''):
        """Write a provided configuration back to the configuration file."""
        config = self.get_config()
        callback_function(config)
        ConfigFile._writeJSON(config, self.config_file)
        self.config = config
        self.gitAdd(reason)
        self.setConfigPermissions()

    def getPermissionConfig(self):
        """Obtain the permission config"""
        config = self.get_config()
        return config['permissions']

    @staticmethod
    def _writeJSON(data, file_name):
        """Parse and writes the JSON VM config file"""
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
        """Create a basic VM configuration for new VMs"""
        raise NotImplementedError

    def setConfigPermissions(self):
        """Set file permissions for config directories"""

        def set_permission(path, directory=True, owner=0):
            """Ser permissions on directory"""
            permission_mode = stat.S_IRUSR
            if directory:
                permission_mode = permission_mode | stat.S_IWUSR | stat.S_IXUSR

            if (directory and os.path.isdir(path) or
                    not directory and os.path.exists(path)):
                os.chown(path, owner, 0)
                os.chmod(path, permission_mode)

        # Set permissions on git directory
        for directory in os.listdir(DirectoryLocation.BASE_STORAGE_DIR):
            path = os.path.join(DirectoryLocation.BASE_STORAGE_DIR, directory)
            if os.path.isdir(path):
                if directory == '.git':
                    set_permission(path, directory=True)
                else:
                    set_permission(os.path.join(path, 'vm'), directory=True)
                    set_permission(os.path.join(path, 'config.json'), directory=False)

        # Set permission for base directory, node directory and ISO directory
        for directory in [DirectoryLocation.BASE_STORAGE_DIR, DirectoryLocation.NODE_STORAGE_DIR,
                          DirectoryLocation.ISO_STORAGE_DIR]:
            set_permission(directory, directory=True,
                           owner=pwd.getpwnam('libvirt-qemu').pw_uid)

    def _upgrade(self, config):
        """Updates the configuration file"""
        raise NotImplementedError

    def upgrade(self):
        """Performs an upgrade of the config file"""
        # Check the version of the configuration file
        current_version = self._getVersion()
        if current_version < self.CURRENT_VERSION:
            def upgradeConfig(config):
                """Update config in config file"""
                # Perform the configuration sub-class specific upgrade
                # tasks
                self._upgrade(config)
                # Update the version number of the configuration file to
                # the current version
                config['version'] = self.CURRENT_VERSION
            self.update_config(
                upgradeConfig,
                'Updated configuration file \'%s\' from version \'%s\' to \'%s\'' %
                (self.config_file,
                 current_version,
                 self.CURRENT_VERSION))

    def _getVersion(self):
        """Return the version number of the configuration file"""
        config = self.get_config()
        if 'version' in config.keys():
            return config['version']
        else:
            return 0

    def gitAdd(self, message=''):
        """Commit changes to an added or modified configuration file"""
        if self._checkGitRepo():
            session_obj = self._get_registered_object('mcvirt_session')
            username = ''
            user = None
            if session_obj:
                try:
                    user = session_obj.get_proxy_user_object()
                except UserDoesNotExistException:
                    pass
            if user:
                username = session_obj.get_proxy_user_object().get_username()
            message += "\nUser: %s\nNode: %s" % (username, get_hostname())
            try:
                System.runCommand([self.GIT, 'add', self.config_file],
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'commit',
                                   '-m',
                                   message,
                                   self.config_file],
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
            except Exception:
                pass

    def gitMove(self, src, dest, message=''):
        """Move git directory, commit and push"""
        if self._checkGitRepo():
            session_obj = self._get_registered_object('mcvirt_session')
            username = ''
            user = None
            if session_obj:
                try:
                    user = session_obj.get_proxy_user_object()
                except UserDoesNotExistException:
                    pass
            if user:
                username = session_obj.get_proxy_user_object().get_username()
            message += "\nUser: %s\nNode: %s" % (username, get_hostname())

            # Perform git move
            System.runCommand(['git', 'mv', src, dest])

            # Attempt to commit and push changes
            try:
                System.runCommand([self.GIT, 'commit', '-m', message],
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
            except Exception:
                pass
        else:
            shutil.move(src, dest)

    def gitRemove(self, message=''):
        """Remove and commits a configuration file"""
        if self._checkGitRepo():
            session_obj = self._get_registered_object('mcvirt_session')
            username = ''
            user = None
            if session_obj:
                try:
                    user = session_obj.get_proxy_user_object()
                except UserDoesNotExistException:
                    pass
            if user:
                username = session_obj.get_proxy_user_object().get_username()
            message += "\nUser: %s\nNode: %s" % (username, get_hostname())
            try:
                System.runCommand([self.GIT,
                                   'rm',
                                   '--cached',
                                   self.config_file],
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
                System.runCommand([self.GIT, 'commit', '-m', message],
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
                System.runCommand([self.GIT,
                                   'push'],
                                  raise_exception_on_failure=False,
                                  cwd=DirectoryLocation.BASE_STORAGE_DIR)
            except Exception:
                pass

    def _checkGitRepo(self):
        """Clone the configuration repo, if necessary, and updates the repo"""
        from mcvirt_config import MCVirtConfig

        # Only attempt to create a git repository if the git
        # URL has been set in the MCVirt configuration
        mcvirt_config = MCVirtConfig().get_config()
        if mcvirt_config['git']['repo_domain'] == '':
            return False

        # Attempt to create git object, if it does not already exist
        if not os.path.isdir(DirectoryLocation.BASE_STORAGE_DIR + '/.git'):

            # Initialise git repository
            System.runCommand([self.GIT, 'init'], cwd=DirectoryLocation.BASE_STORAGE_DIR)

            # Set git name and email address
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               DirectoryLocation.BASE_STORAGE_DIR +
                               '/.git/config', 'user.name', mcvirt_config['git']['commit_name']])
            System.runCommand([self.GIT, 'config', '--file=%s' %
                               DirectoryLocation.BASE_STORAGE_DIR +
                               '/.git/config', 'user.email', mcvirt_config['git']['commit_email']])

            # Create git-credentials store
            System.runCommand([self.GIT,
                               'config',
                               '--file=%s' % DirectoryLocation.BASE_STORAGE_DIR + '/.git/config',
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
                cwd=DirectoryLocation.BASE_STORAGE_DIR)

            # Update the repo
            System.runCommand([self.GIT, 'fetch'], cwd=DirectoryLocation.BASE_STORAGE_DIR)
            System.runCommand([self.GIT, 'checkout', 'master'],
                              cwd=DirectoryLocation.BASE_STORAGE_DIR)
            System.runCommand([self.GIT,
                               'branch',
                               '--set-upstream-to',
                               'origin/master',
                               'master'],
                              cwd=DirectoryLocation.BASE_STORAGE_DIR)

            # Perform an initial commit of the configuration file
            self.gitAdd('Initial commit of configuration file.')

        else:
            # Update repository
            System.runCommand([self.GIT,
                               'pull'],
                              raise_exception_on_failure=False,
                              cwd=DirectoryLocation.BASE_STORAGE_DIR)

        return True

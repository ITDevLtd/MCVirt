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

import unittest
import os
import time
from enum import Enum
import libvirt

from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.exceptions import (VirtualMachineLockException, VmRegisteredElsewhereException,
                               UnsuitableNodeException, VmStoppedException,
                               DrbdVolumeNotInSyncException, DrbdStateException,
                               IsoNotPresentOnDestinationNodeException, MCVirtException)
from mcvirt.cluster.cluster import Cluster
from mcvirt.iso.iso import Iso

from mcvirt.virtual_machine.hard_drive.drbd import DrbdConnectionState, DrbdRoleState
from mcvirt.constants import PowerStates, LockStates, DirectoryLocation
from mcvirt.test.test_base import TestBase, skip_drbd
from mcvirt.libvirt_connector import LibvirtConnector
from mcvirt.virtual_machine.factory import Factory as VirtualMachineFactory
from mcvirt.utils import get_hostname
from mcvirt.rpc.rpc_daemon import RpcNSMixinDaemon
from mcvirt.rpc.expose_method import Expose


class LibvirtFailureMode(Enum):
    """Modes in which the libvirt is directed to simulate a failure"""
    NORMAL_RUN = 0
    CONNECTION_FAILURE = 1
    PRE_MIGRATION_FAILURE = 2
    POST_MIGRATION_FAILURE = 3


class LibvirtFailureSimulationException(MCVirtException):
    """A libvirt command has been simulated to fail"""
    pass


class LibvirtConnectorUnitTest(LibvirtConnector):
    """Override LibvirtConnector class to provide ability to cause
       connection errors whilst connecting to remote libvirt instances"""

    def get_connection(self, server=None):
        if not (server is None or server == 'localhost' or server == get_hostname()):
            server = 'doesnnotexist.notavalidrootdomain'
        return super(LibvirtConnectorUnitTest, self).get_connection(server)


class VirtualMachineFactoryUnitTest(VirtualMachineFactory):

    @Expose()
    def get_virtual_machine_by_id(self, vm_id):
        """Obtain a VM object, based on VM name"""
        # If not, create object, register with pyro
        # and store in cached object dict
        vm_object = VirtualMachineLibvirtFail(self, vm_id)
        self._register_object(vm_object)
        vm_object.initialise()
        return vm_object


class VirtualMachineLibvirtFail(VirtualMachine):
    """Override the VirtulMachine class to add overrides for simulating
    libvirt failures.
    """

    LIBVIRT_FAILURE_MODE = LibvirtFailureMode.NORMAL_RUN

    def _get_libvirt_domain_object(self, allow_remote=False):
        """Obtains the libvirt domain object and, if specified, overrides the migrate3
        method to simulate different failure cases
        """
        libvirt_object = super(VirtualMachineLibvirtFail, self)._get_libvirt_domain_object(
            allow_remote=False
        )

        if (VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE is
                LibvirtFailureMode.PRE_MIGRATION_FAILURE):

            # Override migrate3 method to raise an exception before the migration takes place
            def migrate3(self, *args, **kwargs):
                """Raise exception for pre-migration failure"""
                raise LibvirtFailureSimulationException('Pre-migration failure')

            # Bind overridden migrate3 method to libvirt object
            function_type = type(libvirt.virDomain.migrate3)
            libvirt_object.migrate3 = function_type(migrate3, libvirt_object, libvirt.virDomain)

        elif (VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE is
                LibvirtFailureMode.POST_MIGRATION_FAILURE):
            # Override the migrate3 method to raise an exception
            # after the migration has taken place
            def migrate3(self, *args, **kwargs):
                """Raise post migration failure"""
                libvirt.virDomain.migrate3(libvirt_object, *args, **kwargs)
                raise LibvirtFailureSimulationException('Post-migration failure')

            # Bind overridden migrate3 method to libvirt object
            function_type = type(libvirt.virDomain.migrate3)
            libvirt_object.migrate3 = function_type(migrate3, libvirt_object, libvirt.virDomain)

        return libvirt_object


class OnlineMigrateTests(TestBase):
    """Provides unit tests for the onlineMigrate function"""

    RPC_DAEMON = None

    @staticmethod
    def suite():
        """Return a test suite of the online migrate tests"""
        suite = unittest.TestSuite()
        suite.addTest(OnlineMigrateTests('test_migrate_locked'))
        suite.addTest(OnlineMigrateTests('test_migrate_unregistered'))
        suite.addTest(OnlineMigrateTests('test_migrate_inappropriate_node'))
        suite.addTest(OnlineMigrateTests('test_migrate_drbd_not_connected'))
        suite.addTest(OnlineMigrateTests('test_migrate_invalid_network'))
        suite.addTest(OnlineMigrateTests('test_migrate_invalid_iso'))
        suite.addTest(OnlineMigrateTests('test_migrate_invalid_node'))
        suite.addTest(OnlineMigrateTests('test_migrate_pre_migration_libvirt_failure'))
        suite.addTest(OnlineMigrateTests('test_migrate_post_migration_libvirt_failure'))
        suite.addTest(OnlineMigrateTests('test_migrate_libvirt_connection_failure'))
        suite.addTest(OnlineMigrateTests('test_migrate_stopped_vm'))
        suite.addTest(OnlineMigrateTests('test_migrate'))
        return suite

    def setUp(self):
        """Create various objects and deletes any test VMs"""
        # Register fake libvirt connector with daemon
        self.old_libvirt_connector = RpcNSMixinDaemon.DAEMON.registered_factories[
            'libvirt_connector'
        ]
        OnlineMigrateTests.RPC_DAEMON.register(LibvirtConnectorUnitTest(),
                                               objectId='libvirt_connector',
                                               force=True)
        self.old_virtual_machine_factory = RpcNSMixinDaemon.DAEMON.registered_factories[
            'virtual_machine_factory'
        ]
        vm_factory = VirtualMachineFactoryUnitTest()
        OnlineMigrateTests.RPC_DAEMON.register(vm_factory,
                                               objectId='virtual_machine_factory',
                                               force=True)

        super(OnlineMigrateTests, self).setUp()

        if not self.rpc.get_connection('node_drbd').is_enabled():
            self.skipTest('DRBD is not enabled on this node')

        self.test_iso = 'test_iso.iso'
        self.test_iso_path = '%s/%s' % (DirectoryLocation.ISO_STORAGE_DIR, self.test_iso)

        self.test_vm_object = self.create_vm('TEST_VM_1', 'Drbd')
        self.local_vm_object = vm_factory.get_virtual_machine_by_name(
            self.test_vms['TEST_VM_1']['name']
        )

        # Wait until the Drbd resource is synced
        time.sleep(5)
        for disk_object in self.local_vm_object.get_hard_drive_objects():
            wait_timeout = 6
            while disk_object.drbdGetConnectionState()[1] != DrbdConnectionState.CONNECTED.value:
                # If the Drbd volume has not connected within 1 minute, throw an exception
                if not wait_timeout:
                    raise DrbdVolumeNotInSyncException('Wait for Drbd connection timed out')

                time.sleep(10)
                wait_timeout -= 1
        self.local_vm_object.start()

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Remove the test ISO, if it exists
        if os.path.isfile(self.test_iso_path):
            os.unlink(self.test_iso_path)

        # Register original libvirt connector object
        OnlineMigrateTests.RPC_DAEMON.register(self.old_libvirt_connector,
                                               objectId='libvirt_connector',
                                               force=True)
        OnlineMigrateTests.RPC_DAEMON.register(self.old_virtual_machine_factory,
                                               objectId='virtual_machine_factory',
                                               force=True)

        super(OnlineMigrateTests, self).tearDown()

    @skip_drbd(True)
    def test_migrate_locked(self):
        """Attempts to migrate a locked VM"""
        self.local_vm_object._setLockState(LockStates.LOCKED)

        with self.assertRaises(VirtualMachineLockException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

    @skip_drbd(True)
    def test_migrate_unregistered(self):
        """Attempts to migrate a VM that is not registered"""
        self.local_vm_object.stop()

        # Unregister VM
        self.local_vm_object.unregister()

        # Attempt to migrate VM
        with self.assertRaises(VmRegisteredElsewhereException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

    @skip_drbd(True)
    def test_migrate_inappropriate_node(self):
        """Attempts to migrate a VM to a node that is not part of
           its available nodes"""
        remote_node = self.local_vm_object._get_remote_nodes()[0]

        def remote_node_config(config):
            """Remove node from VM config"""
            config['available_nodes'].remove(remote_node)
        self.local_vm_object.get_config_object().update_config(remote_node_config)

        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate(remote_node)

        def add_node_config(config):
            """Update available nodes config"""
            config['available_nodes'].append(remote_node)
        self.local_vm_object.get_config_object().update_config(add_node_config)

    @skip_drbd(True)
    def test_migrate_drbd_not_connected(self):
        """Attempts to migrate a VM whilst Drbd is not connected"""
        for disk_object in self.local_vm_object.get_hard_drive_objects():
            disk_object._drbdDisconnect()

        with self.assertRaises(DrbdStateException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

    @skip_drbd(True)
    def test_migrate_invalid_network(self):
        """Attempts to migrate a VM attached to a network that doesn't exist
           on the destination node"""
        # Replace the network in VM network adapters with an invalid network
        def set_invalid_network(config):
            """Set invalid network name"""
            for mac_address in config['network_interfaces']:
                config['network_interfaces'][mac_address] = 'Non-existent-network'
        self.local_vm_object.get_config_object().update_config(set_invalid_network)

        # Attempt to migrate the VM
        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

        # Reset the VM configuration
        def resetNetwork(config):
            """Reset network config"""
            for mac_address in config['network_interfaces']:
                config['network_interfaces'][mac_address] = self.test_vms[
                    'TEST_VM_1'
                ]['networks'][0]
        self.local_vm_object.get_config_object().update_config(resetNetwork)

    @skip_drbd(True)
    def test_migrate_invalid_iso(self):
        """Attempts to migrate a VM, with an ISO attached that doesn't exist
           on the destination node"""
        # Create test ISO
        fhandle = open(self.test_iso_path, 'a')
        try:
            os.utime(self.test_iso_path, None)
        finally:
            fhandle.close()

        # Stop VM and attach ISO
        self.local_vm_object.stop()
        iso_factory = self.rpc.get_connection('iso_factory')
        iso_object = iso_factory.get_iso_by_name(self.test_iso)
        self.rpc.annotate_object(iso_object)
        self.local_vm_object.start(iso_object)

        # Attempt to migrate VM
        with self.assertRaises(IsoNotPresentOnDestinationNodeException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

    @skip_drbd(True)
    def test_migrate_invalid_node(self):
        """Attempts to migrate the VM to a non-existent node"""
        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate('non-existent-node')

    @skip_drbd(True)
    def test_migrate_pre_migration_libvirt_failure(self):
        """Simulates a pre-migration libvirt failure"""
        # Set the mcvirt libvirt failure mode to simulate a pre-migration failure
        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.PRE_MIGRATION_FAILURE

        # Attempt to perform a migration
        with self.assertRaises(LibvirtFailureSimulationException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the local node and in a running state
        self.assertEqual(self.local_vm_object.getNode(), get_hostname())
        self.assertEqual(self.local_vm_object.getPowerState(), PowerStates.RUNNING.value)

        # Ensure that the VM is registered with the local libvirt instance and not on the remote
        # libvirt instance
        self.assertTrue(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=get_hostname())
        )
        self.assertFalse(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=self.local_vm_object._get_remote_nodes()[0])
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.local_vm_object.get_hard_drive_objects():
            # Check that the disk is shown as not in-sync
            with self.assertRaises(DrbdVolumeNotInSyncException):
                disk_object._checkDrbdStatus()

            # Reset disk sync status and re-check status to ensure
            # the disk is otherwise in a valid state
            disk_object.setSyncState(True)
            disk_object._checkDrbdStatus()

            # Ensure that the local and remote disks are in the correct Drbd role
            local_role, remote_role = disk_object._drbdGetRole()
            self.assertEqual(local_role, DrbdRoleState.PRIMARY)
            self.assertEqual(remote_role, DrbdRoleState.SECONDARY)

    @skip_drbd(True)
    def test_migrate_post_migration_libvirt_failure(self):
        """Simulates a post-migration libvirt failure"""
        # Set the mcvirt libvirt failure mode to simulate a post-migration failure
        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.POST_MIGRATION_FAILURE

        # Attempt to perform a migration
        with self.assertRaises(LibvirtFailureSimulationException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the remote node and in a running state
        self.assertEqual(self.local_vm_object.getNode(),
                         self.local_vm_object._get_remote_nodes()[0])
        self.assertEqual(self.local_vm_object.getPowerState(), PowerStates.RUNNING)

        # Ensure that the VM is registered with the remote libvirt instance and not on the local
        # libvirt instance
        self.assertFalse(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=get_hostname())
        )
        self.assertTrue(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=self.local_vm_object._get_remote_nodes()[0])
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.local_vm_object.get_hard_drive_objects():
            # Check that the disk is shown as not in-sync
            with self.assertRaises(DrbdVolumeNotInSyncException):
                disk_object._checkDrbdStatus()

            # Reset disk sync status and re-check status to ensure
            # the disk is otherwise in a valid state
            disk_object.setSyncState(True)
            disk_object._checkDrbdStatus()

            # Ensure that the local and remote disks are in the correct Drbd role
            local_role, remote_role = disk_object._drbdGetRole()
            self.assertEqual(local_role, DrbdRoleState.SECONDARY)
            self.assertEqual(remote_role, DrbdRoleState.PRIMARY)

    @skip_drbd(True)
    def test_migrate_libvirt_connection_failure(self):
        """Attempt to perform a migration, simulating a libvirt
           connection failure"""
        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.CONNECTION_FAILURE

        with self.assertRaises(libvirt.libvirtError):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the local node and in a running state
        self.assertEqual(self.local_vm_object.getNode(), get_hostname())
        self.assertEqual(self.local_vm_object.getPowerState(), PowerStates.RUNNING)

    @skip_drbd(True)
    def test_migrate_stopped_vm(self):
        """Attempts to migrate a stopped VM"""
        self.local_vm_object.stop()

        with self.assertRaises(VmStoppedException):
            self.test_vm_object.onlineMigrate(self.local_vm_object._get_remote_nodes()[0])

    @skip_drbd(True)
    def test_migrate(self):
        "Perform an online migration using the argument parser"
        # Set the mcvirt libvirt failure mode to simulate a post-migration failure
        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.POST_MIGRATION_FAILURE

        # Attempt to perform a migration
        self.parser.parse_arguments("migrate --online --node=%s %s" %
                                    (self.local_vm_object._get_remote_nodes()[0],
                                     self.local_vm_object.get_name()))

        VirtualMachineLibvirtFail.LIBVIRT_FAILURE_MODE = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the remote node and in a running state
        self.assertEqual(self.local_vm_object.getNode(),
                         self.local_vm_object._get_remote_nodes()[0])
        self.assertEqual(self.local_vm_object.getPowerState(), PowerStates.RUNNING.value)

        # Ensure that the VM is registered with the remote libvirt instance and not on the local
        # libvirt instance
        self.assertFalse(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=get_hostname())
        )
        self.assertTrue(
            self.local_vm_object.get_name() in
            self.vm_factory.getAllVmNames(node=self.local_vm_object._get_remote_nodes()[0])
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.local_vm_object.get_hard_drive_objects():
            # Check that the disk is shown as not in-sync
            disk_object._checkDrbdStatus()

            # Ensure that the local and remote disks are in the correct Drbd role
            local_role, remote_role = disk_object._drbdGetRole()
            self.assertEqual(local_role, DrbdRoleState.SECONDARY)
            self.assertEqual(remote_role, DrbdRoleState.PRIMARY)

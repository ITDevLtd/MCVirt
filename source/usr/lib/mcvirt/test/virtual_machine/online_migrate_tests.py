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

from mcvirt.parser import Parser
from mcvirt.node.drbd import Drbd as NodeDrbd
from mcvirt.cluster.remote import Remote
from mcvirt.virtual_machine.virtual_machine import VirtualMachine
from mcvirt.exceptions import (VirtualMachineLockException, VmRegisteredElsewhereException,
                               UnsuitableNodeException, VmStoppedException,
                               DrbdVolumeNotInSyncException, DrbdStateException,
                               IsoNotPresentOnDestinationNodeException, MCVirtException)
from mcvirt.constants import PowerStates
from mcvirt.virtual_machine.hard_drive.drbd import DrbdConnectionState, DrbdRoleState
from mcvirt.cluster.cluster import Cluster
from mcvirt.iso.iso import Iso
from mcvirt.test.test_base import TestBase, skip_drbd


class LibvirtFailureMode(Enum):
    """Modes in which the libvirt is directed to simulate a failure"""
    NORMAL_RUN = 0
    CONNECTION_FAILURE = 1
    PRE_MIGRATION_FAILURE = 2
    POST_MIGRATION_FAILURE = 3


class LibvirtFailureSimulationException(MCVirtException):
    """A libvirt command has been simulated to fail"""
    pass


class DummyRemote(Remote):
    """Provide a dummy instance of a Remote object, for use in
       conjunction with the getRemoteLibvirtConnection method of
       the MCVirt class"""

    def __init__(self, cluster_instance, name, remote_ip, *args, **kwargs):
        """Store the required member variables"""
        self.name = name
        self.remote_ip = remote_ip or '192.168.254.254'

    def __del__(self):
        """Do not perform the super __del__ function"""
        pass


class MCVirtLibvirtFail(MCVirt):
    """Override the MCVirt object to add function overrides
       to simulate failures"""

    def __init__(self, *args, **kwargs):
        """Set test attributes and call super __init__ method"""
        self.libvirt_failure_mode = LibvirtFailureMode.NORMAL_RUN
        return super(MCVirtLibvirtFail, self).__init__(*args, **kwargs)

    def getRemoteLibvirtConnection(self, remote_node):
        """Overrides the getRemoteLibvirtConnection function to
           attempt to simulate an unresponsive remote libvirt daemon"""
        if self.libvirt_failure_mode is LibvirtFailureMode.CONNECTION_FAILURE:
            cluster_instance = Cluster(self)
            remote_node = DummyRemote(cluster_instance,
                                      'invalid_remote_node',
                                      initialise_node=False,
                                      remote_ip='192.168.254.254')
        return super(MCVirtLibvirtFail, self).getRemoteLibvirtConnection(remote_node)


class VirtualMachineLibvirtFail(VirtualMachine):
    """Override the VirtulMachine class to add overrides for simulating
       libvirt failures"""

    def __init__(self, *args, **kwargs):
        return super(VirtualMachineLibvirtFail, self).__init__(*args, **kwargs)

    def _getLibvirtDomainObject(self):
        """Obtains the libvirt domain object and, if specified, overrides the migrate3
           method to simulate different failure cases"""
        libvirt_object = super(VirtualMachineLibvirtFail, self)._getLibvirtDomainObject()

        if self.mcvirt_object.libvirt_failure_mode is LibvirtFailureMode.PRE_MIGRATION_FAILURE:

            # Override migrate3 method to raise an exception before the migration takes place
            def migrate3(self, *args, **kwargs):
                raise LibvirtFailureSimulationException('Pre-migration failure')

            # Bind overridden migrate3 method to libvirt object
            function_type = type(libvirt.virDomain.migrate3)
            libvirt_object.migrate3 = function_type(migrate3, libvirt_object, libvirt.virDomain)

        elif self.mcvirt_object.libvirt_failure_mode is LibvirtFailureMode.POST_MIGRATION_FAILURE:
            # Override the migrate3 method to raise an exception after the migration has taken place
            def migrate3(self, *args, **kwargs):
                libvirt.virDomain.migrate3(libvirt_object, *args, **kwargs)
                raise LibvirtFailureSimulationException('Post-migration failure')

            # Bind overridden migrate3 method to libvirt object
            function_type = type(libvirt.virDomain.migrate3)
            libvirt_object.migrate3 = function_type(migrate3, libvirt_object, libvirt.virDomain)

        return libvirt_object


class OnlineMigrateTests(TestBase):
    """Provides unit tests for the onlineMigrate function"""

    @staticmethod
    def suite():
        """Returns a test suite of the online migrate tests"""
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
        """Creates various objects and deletes any test VMs"""
        # Get an MCVirt instance
        self.mcvirt = MCVirtLibvirtFail()

        # Setup variable for test VM
        self.test_vm = {
            'name': 'mcvirt-unittest-vm',
            'cpu_count': 1,
            'memory_allocation': 100,
            'disk_size': [100],
            'networks': ['Production']
        }

        self.test_iso = 'test_iso.iso'
        self.test_iso_path = '%s/%s' % (self.mcvirt.ISO_STORAGE_DIR, self.test_iso)

        # Ensure any test VM is stopped and removed from the machine
        stop_and_delete(self.mcvirt, self.test_vm['name'])

        # Create virtual machine
        VirtualMachine.create(self.mcvirt, self.test_vm['name'],
                              self.test_vm['cpu_count'],
                              self.test_vm['memory_allocation'],
                              self.test_vm['disk_size'],
                              self.test_vm['networks'],
                              storage_type='Drbd')

        self.test_vm_object = VirtualMachineLibvirtFail(self.mcvirt, self.test_vm['name'])

        # Wait until the Drbd resource is synced
        time.sleep(5)
        for disk_object in self.test_vm_object.getHardDriveObjects():
            wait_timeout = 6
            while (disk_object._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
                # If the Drbd volume has not connected within 1 minute, throw an exception
                if (not wait_timeout):
                    raise DrbdVolumeNotInSyncException('Wait for Drbd connection timed out')

                time.sleep(10)
                wait_timeout -= 1
        self.test_vm_object.start()

    def tearDown(self):
        """Stops and tears down any test VMs"""
        # Ensure any test VM is stopped and removed from the machine
        self.test_vm_object = None
        stop_and_delete(self.mcvirt, self.test_vm['name'])

        # Remove the test ISO, if it exists
        if (os.path.isfile(self.test_iso_path)):
            os.unlink(self.test_iso_path)

        self.mcvirt = None

    def get_remote_node(self):
        """Returns the remote node in the cluster"""
        available_nodes = self.test_vm_object.getAvailableNodes()
        available_nodes.remove(Cluster.getHostname())
        return available_nodes[0]

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_locked(self):
        """Attempts to migrate a locked VM"""
        self.test_vm_object.setLockState(LockStates.LOCKED.value)

        with self.assertRaises(VirtualMachineLockException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_unregistered(self):
        """Attempts to migrate a VM that is not registered"""
        self.test_vm_object.stop()

        # Unregister VM
        self.test_vm_object._unregister()

        # Attempt to migrate VM
        with self.assertRaises(VmRegisteredElsewhereException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_inappropriate_node(self):
        """Attempts to migrate a VM to a node that is not part of
           its available nodes"""
        remote_node = self.get_remote_node()

        def update_config(config):
            config['available_nodes'].remove(remote_node)
        self.test_vm_object.get_config_object().update_config(update_config)

        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate(remote_node)

        def update_config(config):
            config['available_nodes'].append(remote_node)
        self.test_vm_object.get_config_object().update_config(update_config)

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_drbd_not_connected(self):
        """Attempts to migrate a VM whilst Drbd is not connected"""
        for disk_object in self.test_vm_object.getHardDriveObjects():
            disk_object._drbdDisconnect()

        with self.assertRaises(DrbdStateException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

        cluster_instance = Cluster(self.mcvirt)
        node_object = cluster_instance.get_remote_node(self.get_remote_node())

        for disk_object in self.test_vm_object.getHardDriveObjects():
            disk_object._drbdConnect()

            try:
                node_object.run_remote_command('virtual_machine-hard_drive-drbd-drbdConnect',
                                               {'vm_name': self.test_vm_object.get_name(),
                                                'disk_id': disk_object.get_config_object().getId()})
            except:
                pass

        # Wait until the Drbd resource is synced
        for disk_object in self.test_vm_object.getHardDriveObjects():
            wait_timeout = 6
            while (disk_object._drbdGetConnectionState() != DrbdConnectionState.CONNECTED):
                # If the Drbd volume has not connected within 1 minute, throw an exception
                if (not wait_timeout):
                    raise DrbdVolumeNotInSyncException('Wait for Drbd connection timed out')

                time.sleep(10)
                wait_timeout -= 1

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_invalid_network(self):
        """Attempts to migrate a VM attached to a network that doesn't exist
           on the destination node"""
        # Replace the network in VM network adapters with an invalid network
        def setInvalidNetwork(config):
            for mac_address in config['network_interfaces']:
                config['network_interfaces'][mac_address] = 'Non-existent-network'
        self.test_vm_object.get_config_object().update_config(setInvalidNetwork)

        # Attempt to migrate the VM
        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

        # Reset the VM configuration
        def resetNetwork(config):
            for mac_address in config['network_interfaces']:
                config['network_interfaces'][mac_address] = self.test_vm['networks'][0]
        self.test_vm_object.get_config_object().update_config(resetNetwork)

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
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
        self.test_vm_object.stop()
        iso_object = Iso(self.mcvirt, self.test_iso)
        self.test_vm_object.start(iso_object)

        # Attempt to migrate VM
        with self.assertRaises(IsoNotPresentOnDestinationNodeException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_invalid_node(self):
        """Attempts to migrate the VM to a non-existent node"""
        with self.assertRaises(UnsuitableNodeException):
            self.test_vm_object.onlineMigrate('non-existent-node')

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_pre_migration_libvirt_failure(self):
        """Simulates a pre-migration libvirt failure"""
        # Set the mcvirt libvirt failure mode to simulate a pre-migration failure
        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.PRE_MIGRATION_FAILURE

        # Attempt to perform a migration
        with self.assertRaises(LibvirtFailureSimulationException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the local node and in a running state
        self.assertEqual(self.test_vm_object.getNode(), Cluster.getHostname())
        self.assertEqual(self.test_vm_object.getState(), PowerStates.RUNNING)

        # Ensure that the VM is registered with the local libvirt instance and not on the remote
        # libvirt instance
        self.assertTrue(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=Cluster.getHostname())
        )
        self.assertFalse(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=self.get_remote_node())
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.test_vm_object.getHardDriveObjects():
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

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_post_migration_libvirt_failure(self):
        """Simulates a post-migration libvirt failure"""
        # Set the mcvirt libvirt failure mode to simulate a post-migration failure
        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.POST_MIGRATION_FAILURE

        # Attempt to perform a migration
        with self.assertRaises(LibvirtFailureSimulationException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the remote node and in a running state
        self.assertEqual(self.test_vm_object.getNode(), self.get_remote_node())
        self.assertEqual(self.test_vm_object.getState(), PowerStates.RUNNING)

        # Ensure that the VM is registered with the remote libvirt instance and not on the local
        # libvirt instance
        self.assertFalse(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=Cluster.getHostname())
        )
        self.assertTrue(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=self.get_remote_node())
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.test_vm_object.getHardDriveObjects():
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

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_libvirt_connection_failure(self):
        """Attempt to perform a migration, simulating a libvirt
           connection failure"""
        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.CONNECTION_FAILURE

        with self.assertRaises(libvirt.libvirtError):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the local node and in a running state
        self.assertEqual(self.test_vm_object.getNode(), Cluster.getHostname())
        self.assertEqual(self.test_vm_object.getState(), PowerStates.RUNNING)

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate_stopped_vm(self):
        """Attempts to migrate a stopped VM"""
        self.test_vm_object.stop()

        with self.assertRaises(VmStoppedException):
            self.test_vm_object.onlineMigrate(self.get_remote_node())

    @unittest.skipIf(not NodeDrbd.is_enabled(),
                     'Drbd is not enabled on this node')
    def test_migrate(self):
        "Perform an online migration using the argument parser"
        # Set the mcvirt libvirt failure mode to simulate a post-migration failure
        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.POST_MIGRATION_FAILURE

        # Attempt to perform a migration
        self.parser.parse_arguments("migrate --online --node=%s %s" %
                                    (self.get_remote_node(),
                                     self.test_vm_object.get_name()),
                                    mcvirt_instance=self.mcvirt)

        self.mcvirt.libvirt_failure_mode = LibvirtFailureMode.NORMAL_RUN

        # Ensure the VM is still registered on the remote node and in a running state
        self.assertEqual(self.test_vm_object.getNode(), self.get_remote_node())
        self.assertEqual(self.test_vm_object.getState(), PowerStates.RUNNING)

        # Ensure that the VM is registered with the remote libvirt instance and not on the local
        # libvirt instance
        self.assertFalse(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=Cluster.getHostname())
        )
        self.assertTrue(
            self.test_vm_object.get_name() in
            VirtualMachine.getAllVms(self.mcvirt,
                                     node=self.get_remote_node())
        )

        # Ensure Drbd disks are in a valid state
        for disk_object in self.test_vm_object.getHardDriveObjects():
            # Check that the disk is shown as not in-sync
            disk_object._checkDrbdStatus()

            # Ensure that the local and remote disks are in the correct Drbd role
            local_role, remote_role = disk_object._drbdGetRole()
            self.assertEqual(local_role, DrbdRoleState.SECONDARY)
            self.assertEqual(remote_role, DrbdRoleState.PRIMARY)

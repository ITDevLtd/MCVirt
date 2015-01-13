#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import sys
import unittest

sys.path.insert(0, '/usr/lib')

from mcvirt.test.node.network_tests import NetworkTests
from mcvirt.test.virtual_machine.virtual_machine_tests import VirtualMachineTests

if __name__ == '__main__':
  runner = unittest.TextTestRunner()
  virtual_machine_test_suite = VirtualMachineTests.suite()
  network_test_suite = NetworkTests.suite()
  all_tests = unittest.TestSuite([virtual_machine_test_suite, network_test_suite])
  runner.run(all_tests)
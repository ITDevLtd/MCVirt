#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import getpass
import subprocess
import sys

from mcvirt import MCVirtException

class MCVirtCommandException(MCVirtException):
  """Provides an exception to be thrown after errors whilst calling external commands"""
  pass

class System:

  @staticmethod
  def runCommand(command_args, raise_exception_on_failure=True, cwd=None):
    """Runs system command, throwing an exception if the exit code is not 0"""
    command_process = subprocess.Popen(command_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    if (command_process.wait() and raise_exception_on_failure):
      raise MCVirtCommandException("Command: %s\nExit code: %s\nOutput:\n%s" %
        (' '.join(command_args), command_process.returncode, command_process.stdout.read() + command_process.stderr.read()))
    return (command_process.returncode, command_process.stdout.read(), command_process.stderr.read())

  @staticmethod
  def getUserInput(display_text, password=False):
    """Prompts the user for input"""
    if (password):
      return getpass.getpass(display_text)
    else:
      sys.stdout.write(display_text)
      return sys.stdin.readline()
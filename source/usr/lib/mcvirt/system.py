#
# Copyright I.T. Dev Ltd 2014
# http://www.itdev.co.uk
#
import getpass
import subprocess
import sys

class System:

  @staticmethod
  def runCommand(command_args):
    """Runs system command, throwing an exception if the exit code is not 0"""
    command_process = subprocess.Popen(command_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if (command_process.wait()):
      raise McVirtCommandException("Command: %s\nExit code: %s\nOutput:\n%s" %
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
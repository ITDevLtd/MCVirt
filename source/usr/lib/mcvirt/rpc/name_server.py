from Pyro4 import naming
import threading

class NameServer(threading.Thread):
    """Thread for running the name server"""

    def run(self):
        """Start the Pyro name server"""
        naming.startNSloop(enableBroadcast=False)

from Pyro4 import naming
import threading
import time

class NameServer(threading.Thread):
    """Thread for running the name server"""

    def run(self):
        """Start the Pyro name server"""
        naming.startNSloop(host='0.0.0.0', port=9090, enableBroadcast=False)

    def obtainConnection(self):
        while 1:
            try:
                ns = naming.locateNS(host='127.0.0.1', port=9090, broadcast=False)
                ns = None
                return
            except:
                # Wait for 1 second for name server to come up
                time.sleep(1)

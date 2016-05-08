class PyroObject(object):
    """Base class for providing Pyro-based methods for objects"""

    @property
    def _pyro_initialised(self):
        """Determines if object is registered with the Pyro deamon"""
        return ('_pyroDaemon' in self.__dict__.keys())

    def _register_object(self, local_object):
        """Registers an object with the pyro daemon"""
        if self._pyro_initialised:
            self._pyroDaemon.register(local_object)

    def _convert_remote_object(self, remote_object):
        """Returns a local instance of a remote object"""
        # Ensure that object is a remote object
        if self._pyro_initialised:
            # Obtain daemon instance of object
            return self._pyroDaemon.objectsById[remote_object._pyroUri.object]
        else:
            return remote_object

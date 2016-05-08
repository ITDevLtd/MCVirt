import Pyro4

from user import User
from mcvirt.rpc.pyro_object import PyroObject

class Factory(PyroObject):
    """Class for obtaining user objects"""

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    @Pyro4.expose()
    def get_user_by_username(self, username):
        """Obtains a user object for the given username"""
        user_object = User(username=username)
        self._register_object(user_object)
        return user_object

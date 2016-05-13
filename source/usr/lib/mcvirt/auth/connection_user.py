from user_base import UserBase

class ConnectionUser(UserBase):
    """User type for initial connection users"""

    USER_PREFIX = 'mcv-connection-'
    CAN_GENERATE = True

    def getUsername(self):
        """If a calling user is defined, this should be returned"""
        if 'user_for' in dir(Pyro4.current_context) and Puro4.current_context.user_for:
            return Pyro4.current_context.user_for
        else:
            return self._username

from user_base import UserBase

class ConnectionUser(UserBase):
    """User type for initial connection users"""

    USER_PREFIX = 'mcv-connection-'
    CAN_GENERATE = True

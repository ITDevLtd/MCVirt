import socket

def get_hostname():
    """Returns the hostname of the system"""
    return socket.gethostname()

def get_all_submodules(target_class):
    """Returns all inheriting classes, recursively"""
    subclasses = []
    for subclass in target_class.__subclasses__():
        subclasses.append(subclass)
        subclasses += get_all_submodules(subclass)
    return subclasses

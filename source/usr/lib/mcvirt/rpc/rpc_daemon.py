import atexit
import Pyro4

from mcvirt.mcvirt import MCVirt, MCVirtException
from mcvirt.auth.auth import Auth
from mcvirt.virtual_machine.factory import Factory as VirtualMachineFactory


class BaseRpcDaemon(Pyro4.Daemon):
    """Override Pyro daemon to add authentication checks and MCVirt integration"""
    def __init__(self, mcvirt_instance, *args, **kwargs):
        """Override init to set required configuration and create nameserver connection"""
        # Require all methods/classes to be exposed
        # DO NOT CHANGE THIS OPTION!
        Pyro4.config.REQUIRE_EXPOSE = True

        # Perform super method for init of daemon
        super(BaseRpcDaemon, self).__init__(*args, **kwargs)

        # Store MCVirt instance
        self.mcvirt_instance = mcvirt_instance
        self.user_sessions = {}

    @atexit.register
    def destroy(self):
        # Create MCVirt instance
        self.mcvirt_instance = None

    def validateHandshake(self, conn, data):
        """Perform authentication on new connections"""
        # Reset session_id for current context
        Pyro4.current_context.session_id = None

        # Check and store username from connection
        if 'USER' not in data:
            raise Pyro4.errors.SecurityError('Username and password or Session must be passed')
        username = str(data['USER'])

        # If a password has been provided
        if 'PASS' in data:
            # Store the password and perform authentication check
            password = str(data['PASS'])
            if (Auth.authenticate(username=username, password=password)):
                # Generate a session ID, store and return to clinet
                session_id = uuid.uuid4().hex
                self.user_sessions[session_id] = {'username': username}
                Pyro4.current_context.session_id = session_id
                return session_id

        # If a session id has been passed, store it and check the session_id/username against active sessions
        elif 'SEID' in data:
            session_id = str(data['SEID'])
            if (session_id in self.user_sessions and
                    self.user_sessions[session_id]['username'] == username):
                Pyro4.current_context.session_id = session_id
                return session_id

        # If no valid authentication was provided, raise an error
        raise Pyro4.errors.SecurityError('Invalid username/password/session')


class RpcNSMixinDaemon(object):
    def __init__(self, name_server):
        # Store nameserver, MCVirt instance and create daemon
        self.name_server = name_server
        self.mcvirt_instance = MCVirt()
        self.daemon = BaseRpcDaemon(mcvirt_instance=self.mcvirt_instance)

    def start(self):
        self.daemon.requestLoop()

    def register(self, obj_or_class, objectId, *args, **kwargs):
        """Override register to register object with NS"""
        uri = self.daemon.register(obj_or_class, *args, **kwargs)
        self._nameserver.register(objectId, uri)
        return uri

    def registerFactories(self):
        """Register base MCVirt factories with RPC daemon"""
        # Create Virtual machine factory object and register with daemon
        virtual_machine_factory = VirtualMachineFactory(self.mcvirt_instance)
        self.daemon.register(virtual_machine_factory, objectId='virtual_machine_factory', force=True)

    @atexit.register
    def destroy(self):
        # Create MCVirt instance
        self.mcvirt_instance = None

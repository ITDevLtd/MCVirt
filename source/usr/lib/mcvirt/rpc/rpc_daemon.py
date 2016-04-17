import Pyro4

from mcvirt.mcvirt import MCVirtException
from mcvirt.auth.auth import Auth


class RpcDaemon(Pyro4.Daemon):
    """Override Pyro daemon to add authentication checks and MCVirt integration"""
    def __init__(self, mcvirt_instance, *args, **kwargs):
        """Override init to set required configuration and create nameserver connection"""
        # Require all methods/classes to be exposed
        # DO NOT CHANGE THIS OPTION!
        Pyro4.config.REQUIRE_EXPOSE = True

        # Create and store object for name server connection
        self.ns = Pyro4.naming.locateNS(host='localhost', port=9090, broadcast=False)

        # Perform super method for init of daemon
        super(RpcDaemon, self).__init__(*args, **kwargs)

        # Store MCVirt instance
        self.mcvirt_instance = mcvirt_instance
        self.user_sessions = {}

    def register(self, *args, **kwargs):
        """Override register to register object with NS"""
        uri = super(RpcDaemon, self).register(*args, **kwargs)
        self.ns.register(args[0], uri)
        return uri


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

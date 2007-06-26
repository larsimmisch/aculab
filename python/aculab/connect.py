'''Connect two duplex entity or tuples of simplex entities.'''

from busses import DefaultBus, Connection
from speech import SpeechChannel
from callcontrol import CallHandle

def connect(a, b, bus=DefaultBus()):
    """Create a duplex connection between a and b.

    @param a: a duplex capable entity (like a CallHandle or a SpeechChannel)
        or a tuple of (tx, rx).
        
    @param b: a duplex capable entity (like a CallHandle or a SpeechChannel)
        or a tuple of (tx, rx).

    @return: A L{Connection} object containing all endpoints and timeslots
        allocated for the connection. This object will dissolve the
        connection when it is deleted.

    B{Note}: Ignoring the return value will immediately dissolve the
    connection. Don't do that.
    """

    # Make sure CallChannel is the first argument (if one present)
    if isinstance(a, SpeechChannel) and isinstance(b, CallHandle):
        return connect(b, a, bus)

    c = Connection(bus)

    # SpeechChannel to SpeechChannel
    if isinstance(a, SpeechChannel) and isinstance(b, SpeechChannel):
        if a.info.card == b.info.card:
            if a == b:
                c.timeslots = [ bus.allocate() ]
                c.connections = [a.speak_to(c.timeslots[0]),
                                 b.listen_to(c.timeslots[0])]
            else:
                # connect directly
                c.connections = [a.listen_to((b.info.ost,
                                              b.info.ots)),
                                 b.listen_to((a.info.ost,
                                              a.info.ots))]
        else:
            # allocate two timeslots
            c.timeslots = [ bus.allocate(), bus.allocate() ]
            # make connections
            c.connections = [ b.speak_to(c.timeslots[0]),
                              a.listen_to(c.timeslots[0]),
                              a.speak_to(c.timeslots[1]),
                              b.listen_to(c.timeslots[1]) ]

        return c

    if isinstance(a, CallHandle):
        
        # CallHandle to CallHandle
        if isinstance(b, CallHandle):
            if a.switch == b.switch:
                # connect directly
                c.endpoints = [a.listen_to((b.details.stream,
                                            b.details.ts)),
                               b.listen_to((a.details.stream,
                                            a.details.ts))]
            else:
                # allocate two timeslots
                c.timeslots = [ bus.allocate(), bus.allocate() ]
                # make endpoints
                c.endpoints = [ b.speak_to(c.timeslots[0]),
                                a.listen_to(c.timeslots[0]),
                                a.speak_to(c.timeslots[1]),
                                b.listen_to(c.timeslots[1]) ]

            return c

        # CallHandle to SpeechChannel
        if isinstance(b, SpeechChannel):
            if a.switch == b.info.card:
                # connect directly
                c.endpoints = [a.listen_to((b.info.ost,
                                            b.info.ots)),
                               b.listen_to((a.details.stream,
                                            a.details.ts))]
            else:
                # allocate two timeslots
                c.timeslots = [ bus.allocate(), bus.allocate() ]
                # make endpoints
                c.endpoints = [ b.speak_to(c.timeslots[0]),
                                a.listen_to(c.timeslots[0]),
                                a.speak_to(c.timeslots[1]),
                                b.listen_to(c.timeslots[1]) ]
        
            return c

    raise ValueError('Cannot connect %s and %s', str(a), str(b))

class Glue(object):
    """Glue logic to tie a SpeechChannel to a Call.

    This class is meant to be a base-class for the data of a single call
    with a Prosody channel for speech processing.

    It will allocate a I{SpeechChannel} upon creation and connect it to the
    call.
    When deleted, it will close and disconnect the I{SpeechChannel}."""
    
    def __init__(self, controller, module, call):
        """Allocate a speech channel on module and connect it to the call.

        @param controller: The controller will be passed to the SpeechChannel
        @param module: The module to open the SpeechChannel on. May be either
            a C{tSMModuleId} or an offset.
        @param call: The call that the SpeechChannel will be connected to."""
        
        self.call = call
        # initialize to None in case an exception is raised
        self.speech = None
        self.connection = None
        call.user_data = self
        self.speech = SpeechChannel(controller, module, user_data = self)
        self.connection = connect(call, self.speech)

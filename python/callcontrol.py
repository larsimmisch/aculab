import sys
import getopt
import aculab
import aculab_names as names

class CallEventDispatcher:

    def __init__(self):
        self.calls = {}

    # must only be called from a dispatched event
    # - not from a separate thread
    def add(self, call):
        self.calls[call.handle] = call

    # must only be called from a dispatched event
    # - not from a separate thread
    def remove(self, call):
        del self.calls[call.handle]

    def run(self):
        event = aculab.STATE_XPARMS()
        
        while 1:
            if not self.calls:
                return
            
            event.handle = 0
            event.timeout = 1000

            handled = 0

            rc = aculab.call_event(event)

            handled = ''
            
            # call the event handlers
            if event.handle:
                call = self.calls[event.handle]
                ev = names.event[event.state].lower()
                # let the call handle events first
                try:
                    m = getattr(call, ev)
                    m()
                    handled = '(call'
                except AttributeError:
                    if hasattr(call, ev):
                        raise
                except:
                    raise

                # pass the event on to the controller
                try:
                    m = getattr(call.controller, ev)
                    m(call)
                    if handled:
                        handled += ', controller)'
                    else:
                        handled = '(controller)'
                except AttributeError:
                    if handled:
                        handled += ')'
                    if hasattr(call.controller, ev):
                        raise
                except:
                    raise
                
                if not handled:
                    handled = '(ignored)'

                print hex(event.handle), ev, handled


dispatcher = CallEventDispatcher()

# The CallHandle class models a call handle, as defined by Aculab,
# and common operations on it. Event handling is delegated to the controller,
# in classical OO decomposition.

class Call:

    def __init__(self, controller, port = 0, number = '', timeslot = -1):
        self.controller = controller
        self.port = port
        if number:
            self.number = number
        self.timeslot = timeslot

        self.restart()

    def restart(self):
        if hasattr(self, 'number'):
            self.openout()
        else:
            self.openin()
            
    def openin(self):
        inparms = aculab.IN_XPARMS()
        inparms.net = self.port
        inparms.ts = self.timeslot
        inparms.cnf = aculab.CNF_REM_DISC | aculab.CNF_TSPREFER

        aculab.call_openin(inparms)
        self.handle = inparms.handle

        dispatcher.add(self)

    def openout(self):
        outparms = aculab.OUT_XPARMS()
        outparms.net = self.port
        outparms.ts = self.timeslot
        outparms.cnf = aculab.CNF_REM_DISC | aculab.CNF_TSPREFER
        outparms.sending_complete = 1
        outparms.originating_address = '3172542'
        outparms.destination_address = self.number

        aculab.call_openout(outparms)
        self.handle = outparms.handle

        dispatcher.add(self)

    def listen_to(sink, source):
        "sink and source are tuples of timeslots"
        output = aculab.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = aculab.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        sw = call_port_2_swdrvr(self.port)

        sw_set_output(sw, output)

    def get_details(self):
        self.details = aculab.DETAIL_XPARMS()
        self.details.handle = self.handle

        aculab.call_details(self.details)

        return self.details

    def accept(self):
        aculab.call_accept(self.handle)        

    def disconnect(self, cause = 0):
        if self.handle:
            causeparms = aculab.CAUSE_XPARMS()
            causeparms.handle = self.handle
            causeparms.cause = cause
            aculab.call_disconnect(causeparms)

    def ev_incoming_call_det(self):
        self.get_details()

    def ev_outgoing_ringing(self):
        self.get_details()

    def ev_idle(self):
        dispatcher.remove(self)
        cause = aculab.CAUSE_XPARMS()
        cause.handle = self.handle

        self.handle = None

        if hasattr(self, 'details'):
            del self.details

        if hasattr(self, 'number'):
            del self.number

        aculab.call_release(cause)

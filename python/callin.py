import sys
import getopt
import aculab
import aculab_names as names
import __main__

def usage():
    print 'callin.py [-p <port>]'
    
port = 0

options, args = getopt.getopt(sys.argv[1:], 'p:')

for o, a in options:
    if o == '-p':
        port = int(a)
    else:
        usage()

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

            rc = aculab.call_event(event)
            # call the event handler
            if event.handle:
                call = self.calls[event.handle]
                ev = names.event[event.state].lower()
                print hex(event.handle), ev
                # if the call has an observer, call it, too
                if call.observer and hasattr(call.observer, ev):
                    call.observer.__class__.__dict__[ev](call.observer, call)
                call.__class__.__dict__[ev](call)

dispatcher = CallEventDispatcher()

class Call:

    # restart is silently ignored for outbound calls
    def __init__(self, port = 0, timeslot = -1, number = '',
                 observer = None, restart = 1):
        
        self.port = port
        self.timeslot = timeslot
        self.observer = observer
        
        if number:
            self.restart = 0
            self.openout(number)
        else:
            self.restart = restart
            self.openin()
            
    def openin(self):
        inparms = aculab.IN_XPARMS()
        inparms.net = self.port
        inparms.ts = self.timeslot
        inparms.cnf = aculab.CNF_REM_DISC | aculab.CNF_TSPREFER

        aculab.call_openin(inparms)
        self.handle = inparms.handle

        dispatcher.add(self)

    def openout(self, number):
        self.number = number
        
        outparms = aculab.OUT_XPARMS()
        outparms.net = self.port
        outparms.ts = self.timeslot
        outparms.cnf = aculab.CNF_REM_DISC | aculab.CNF_TSPREFER
        outparms.sending_complete = 1
        outparms.originating_address = '3172542'
        outparms.destination_address = number

        aculab.call_openout(outparms)
        self.handle = outparms.handle

        dispatcher.add(self)

    def disconnect(self, cause = 0):
        causeparms = aculab.CAUSE_XPARMS()
        causeparms.handle = self.handle
        causeparms.cause = cause
        aculab.call_disconnect(causeparms)
        
    def ev_ext_facility(self):
        pass

    def ev_incoming_call_det(self):
        details = aculab.DETAIL_XPARMS()
        details.handle = self.handle

        aculab.call_details(details)

        print 'stream: %d timeslot: %d' % (details.stream, details.ts)
    
        aculab.call_accept(self.handle)

    def ev_wait_for_outgoing(self):
        pass

    def ev_outgoing_ringing(self):
        pass

    def ev_call_connected(self):
        pass

    def ev_remote_disconnect(self):
        self.disconnect()

    def ev_idle(self):
        dispatcher.remove(self)
        cause = aculab.CAUSE_XPARMS()
        cause.handle = self.handle
        aculab.call_release(cause)

        if not hasattr(self, 'number') and self.restart:
            self.openin()
        else:
            if hasattr(self, 'number'):
                del self.number


class TestForward:

    def __init__(self):
        self.incall = Call(port, 1, '', self, 0)

    def ev_incoming_call_det(self, call):
        self.outcall = Call(port, 2, '123', self)

    def ev_remote_disconnect(self, call):
        if call == self.incall:
            self.outcall.disconnect()
        else:
            self.incall.disconnect()

# c = Call(port)

t = TestForward()

dispatcher.run()

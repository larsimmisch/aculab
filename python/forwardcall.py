import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *
from aculab.busses import MVIP
from aculab.names import event_names
import aculab.lowlevel as lowlevel

mvip = MVIP()

def routing_table(port, details):
    "returns the tuple (wait, port, timeslot, destination_address)"
    
    if not details.destination_addr and details.sending_complete:
        return (False, None, None, None)

    if port == 0:
        return (False, 1, 1, '1')
    else:
        return (False, 0, 1, '1')
    
    # return (False, None, None, None)

def find_available_call(port, timeslot = None):
    for c in calls:
        if c.port == port and (c.last_event == lowlevel.EV_WAIT_FOR_INCOMING 
                               or c.last_event == lowlevel.EV_IDLE):
            if timeslot == None or timeslot == c.timeslot:
                return c

    return None

class Forward:

    def __init__(self, incall):
        self.incall = incall
        self.outcall = None
        self.connections = []

        self.route()

    def route(self):
        self.incall.token = self

        if self.outcall:
            # warning: untested (and probably flawed)
            print hex(self.outcall.handle), 'sending:', d.destination_addr
            self.outcall.send_overlap(d.destination_addr,
                                      d.sending_complete)
        else:
            wait, port, timeslot, number = routing_table(self.incall.port,
                                                         self.incall.details)

            if port != None and number:
                print 'making outgoing call', port, timeslot
                self.outcall = find_available_call(port, timeslot)
                if not self.outcall:
                    print hex(self.incall.handle), 'no call available'
                    self.incall.disconnect()
                else:
                    self.outcall.token = self
                    self.outcall.openout(number)
            elif not wait:
                self.incall.disconnect()
            else:
                print hex(self.incall.handle), \
                      'waiting - no destination address'


    def connect(self):
        if not self.connections:
            slots = [mvip.allocate(), mvip.allocate()]

            c = [self.incall.speak_to(slots[0]),
                 self.outcall.listen_to(mvip.invert(slots[0])),
                 self.outcall.speak_to(slots[1]),
                 self.incall.listen_to(mvip.invert(slots[1]))]

            self.connections.extend(c)

    def disconnect(self):
        for c in self.connections:
            if c.ts[0] < 16:
                mvip.free(c.ts)

        self.connections = []
        
class ForwardCallController:
    "controls a single incoming call and its corresponding outgoing call"

    def ev_incoming_call_det(self, call):
        call.token = Forward(call)

    def ev_outgoing_ringing(self, call):
        call.token.connect()
        call.token.incall.incoming_ringing()

    def ev_call_connected(self, call):
        if call == call.token.incall:
            call.token.connect()
        else:
            call.token.incall.accept()

    def ev_remote_disconnect(self, call):
        # if both calls hang up at the same time, disconnect will be called
        # twice, because the calls are set to None only in ev_idle.
        # This should not matter, however.
        if call == call.token.incall:
            if call.token.outcall:
                call.token.outcall.disconnect()
        elif call == call.token.outcall:
            if call.token.incall:
                call.token.incall.disconnect()

        call.disconnect()

    def ev_idle(self, call):
        if call.token:
            call.token.disconnect()
        
            if call == call.token.incall:
                if call.token.outcall:
                    print hex(call.token.outcall.handle), \
                          "disconnecting outgoing call"
                    call.token.outcall.disconnect()            
            elif call == call.token.outcall:
                if call.token.incall:
                    print hex(call.token.incall.handle), \
                          "disconnecting incoming call"
                    call.token.incall.disconnect()
                
            call.token = None

        if not call.handle:
            call.openin()


def usage():
    print 'forwardcall.py [-p <port>]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 2

    options, args = getopt.getopt(sys.argv[1:], 'p:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        else:
            usage()

    dispatcher = CallEventDispatcher()
    controller = ForwardCallController()

    # we should also look at call_signal_info here, but this
    # hasn't been wrapped properly
    calls = [Call(controller, dispatcher, None, p, t) for p in (0, 1)
             for t in (1, 2)]
    
    dispatcher.run()

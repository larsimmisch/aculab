import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *
from aculab.busses import MVIP
from aculab.names import event_names
import aculab.lowlevel as lowlevel

mvip = MVIP()

portmap = { '41': 8, '42': 8, '43': 8, '44': 8,
            '45': 9, '46': 9, '47': 9, '48': 9 }



def routing_table(port, details):
    "returns the tuple (wait, port, timeslot, destination_address)"
    
    if not details.destination_addr and details.sending_complete:
        return (False, None, None, None)

    if port == 0:
        # only forward local calls
        if details.originating_addr in [str(i) for i in range(31, 39)]:
            return (False, portmap[details.destination_addr], details.ts,
                    details.destination_addr)
        else:
            return (True, None, None, None)
        
    elif port in [8, 9]:
        return (False, 0, details.ts,
                details.destination_addr)        
    else:
        return (False, None, None, None)

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
        self.incall.user_data = self

        if self.outcall:
            # warning: untested (and probably flawed)
            print hex(self.outcall.handle), 'sending:', d.destination_addr
            self.outcall.send_overlap(d.destination_addr,
                                      d.sending_complete)
        else:
            wait, port, timeslot, number = routing_table(self.incall.port,
                                                         self.incall.details)

            if port != None and number:
                print 'making outgoing call', port, timeslot, number
                self.outcall = find_available_call(port, timeslot)
                if not self.outcall:
                    print hex(self.incall.handle), 'no call available'
                    self.incall.disconnect()
                else:
                    self.outcall.user_data = self
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
        call.user_data = Forward(call)

    def ev_outgoing_ringing(self, call):
        call.user_data.connect()
        call.user_data.incall.incoming_ringing()

    def ev_call_connected(self, call):
        if call == call.user_data.incall:
            call.user_data.connect()
        else:
            call.user_data.incall.accept()

    def ev_remote_disconnect(self, call):
        # if both calls hang up at the same time, disconnect will be called
        # twice, because the calls are set to None only in ev_idle.
        # This should not matter, however.
        if call == call.user_data.incall:
            if call.user_data.outcall:
                call.user_data.outcall.disconnect()
        elif call == call.user_data.outcall:
            if call.user_data.incall:
                call.user_data.incall.disconnect()

        call.disconnect()

    def ev_idle(self, call):
        if call.user_data:
            call.user_data.disconnect()
        
            if call == call.user_data.incall:
                if call.user_data.outcall:
                    print hex(call.user_data.outcall.handle), \
                          "disconnecting outgoing call"
                    call.user_data.outcall.disconnect()            
            elif call == call.user_data.outcall:
                if call.user_data.incall:
                    print hex(call.user_data.incall.handle), \
                          "disconnecting incoming call"
                    call.user_data.incall.disconnect()
                
            call.user_data = None

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
    calls = [Call(controller, dispatcher, None, 0, t) for t in (1, 2)]
    calls += [Call(controller, dispatcher, None, 8, t) for t in (1, 2)]
    calls += [Call(controller, dispatcher, None, 9, t) for t in (1, 2)]
    
    dispatcher.run()

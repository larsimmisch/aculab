import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *
from aculab.busses import MVIP
import aculab.lowlevel as lowlevel

mvip = MVIP()

class ForwardCallController:
    "controls a single incoming call and its corresponding outgoing call"

    def __init__(self):
        self.incall = None
        self.outcall = None
        self.in_slot = None
        self.out_slot = None
        self.saru_slot = None
        self.connections = []

    def on_details(self):
        d = self.incall.details
        # hang up if no destination address and sending complete
        if not d.destination_addr:
            if d.sending_complete:
                print hex(self.incall.handle), \
                      'error: no destination address but sending_complete'
                self.incall.disconnect()
                return
            else:
                print hex(self.incall.handle), \
                      'waiting - no destination address'
                return

        if self.outcall:
            print hex(self.outcall.handle), 'sending:', d.destination_addr
            self.outcall.send_overlap(d.destination_addr,
                                      d.sending_complete)
        else:
            if d.destination_addr[0] == '9':
                # special case for SARU simulator
                self.incall.accept()
                self.saru_slot = (lowlevel.call_port_2_stream(1), 1)

                switch = lowlevel.call_port_2_swdrvr(1)

                slot = mvip.allocate()
                
                self.in_slot = (self.incall.details.stream,
                                self.incall.details.ts)

                c = [self.incall.listen_to(slot, self.in_slot),
                     mvip.listen_to(switch, self.saru_slot, mvip.invert(slot))]

                self.connections.append(c)
                
            else:
                self.outcall = Call(self, int(d.destination_addr[0]),
                                    d.destination_addr)

    def connect(self):
        if not self.saru_slot:
            slots = [mvip.allocate(), mvip.allocate()]

            self.in_slot = (self.incall.details.stream, self.incall.details.ts)
            self.out_slot = (self.outcall.details.stream,
                             self.outcall.details.ts)

            c = [self.incall.listen_to(slots[0], self.in_slot),
                 self.outcall.listen_to(self.out_slot, mvip.invert(slots[0])),
                 self.outcall.listen_to(slots[1], self.out_slot),
                 self.incall.listen_to(self.in_slot, mvip.invert(slots[1]))]

            self.connections.append(c)

    def disconnect(self):
        for c in self.connections:
            mvip.disable(c[0], c[1])
            if c[1][0] < 16:
                mvip.free(c[1])

        self.connections = []
        self.in_slot = None
        self.out_slot = None
        self.saru_slot = None

    def ev_incoming_call_det(self, call):
        self.incall = call
        self.on_details()

    def ev_ext_hold_request(self, call):
        self.on_details()

    def ev_outgoing_ringing(self, call):
        if self.incall:
            self.incall.incoming_ringing()

    def ev_call_connected(self, call):
        if call == self.incall:
            self.connect()
        else:
            self.incall.accept()

    def ev_remote_disconnect(self, call):
        # if both calls hang up at the same time, disconnect will be called
        # twice, because the calls are set to None only in ev_idle.
        # This should not matter, however.
        if call == self.incall:
            if self.outcall:
                self.outcall.disconnect()
        elif call == self.outcall:
            if self.incall:
                self.incall.disconnect()

        call.disconnect()

    def ev_idle(self, call):
        self.disconnect()
        
        if call == self.incall:
            self.incall = None
            if self.outcall:
                print hex(self.outcall.handle), "disconnecting outgoing call"
                self.outcall.disconnect()
            call.restart()
        elif call == self.outcall:
            self.outcall = None
            if self.incall:
                print hex(self.incall.handle), "disconnecting incoming call"
                self.incall.disconnect()

def usage():
    print 'forwardcall.py [-p <port>]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 2
    controller = ForwardCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:r')

    for o, a in options:
        if o == '-p':
            port = int(a)
        else:
            usage()

    c = Call(controller, port, timeslot = 1)

    dispatcher.run()

import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *

port = 3
outgoing_port = 0

class IncomingCallController:

    def ev_incoming_call_det(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

        call.accept()

    def ev_call_connected(self, call):
        call.listen_to((0, 0), (call.details.stream, call.details.ts))
        st = call_port_2_stream(outgoing)
        call.listen_to((st, 1), (8, 0))
    
    def ev_remote_disconnect(self, call):
        call.disconnect()

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call):
        call.restart()

def usage():
    print 'usage: saru_bridge.py [-p <port>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:o:r')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == 'o':
            outgoing_port = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        else:
            usage()
                
    c = Call(controller, port)

    dispatcher.run()

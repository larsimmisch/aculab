import sys
import getopt
import aculab
import aculab_names as names
from callcontrol import *

class OutgoingCallController:

    def ev_outgoing_ringing(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

    def ev_remote_disconnect(self, call):
        call.disconnect()

class RepeatedOutgoingCallController:

    def ev_idle(self, call):
        call.restart()

def usage():
    print 'callout.py [-p <port>] [-r] number'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:r')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-r':
            controller = RepeatedOutgoingCallController()
        else:
            usage()

    if not len(args):
        usage()
    
    c = Call(controller, port, numberargs[0], 1)

    dispatcher.run()

import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *

class OutgoingCallController:

    def ev_outgoing_ringing(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

    def ev_remote_disconnect(self, call):
        call.disconnect()

class RepeatedOutgoingCallController:

    def ev_idle(self, call):
        call.openout(call.destination_address)

def usage():
    print 'callout.py [-p <port>] [-r] number'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    timeslot = None
    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:rt:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-r':
            controller = RepeatedOutgoingCallController()
        elif o == '-t':
            timeslot = int(a)
        else:
            usage()

    if not len(args):
        usage()

    calldispatcher = CallEventDispatcher()
    
    c = Call(controller, calldispatcher, port=port, timeslot=timeslot)

    c.destination_address = args[0]
    c.openout(args[0])

    calldispatcher.run()

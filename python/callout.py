#!/usr/bin/env python

import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *

class OutgoingCallController:

    def ev_outgoing_ringing(self, call, model):
        log.debug('%s stream: %d timeslot: %d', call.name,
                  call.details.stream, call.details.ts)

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

class RepeatedOutgoingCallController:

    def ev_idle(self, call, model):
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
    
    c = Call(controller,  port=port, timeslot=timeslot)
    c.openout(args[0], 1, '41')

    CallDispatcher.run()

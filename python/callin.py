#!/usr/bin/env python
import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *

class IncomingCallController:

    def ev_incoming_call_det(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

        call.accept()

    def ev_remote_disconnect(self, call):
        call.disconnect()

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call):
        call.openin()

def usage():
    print 'usage: callin.py [-p <port>] [-t <timeslot>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    timeslot = 1
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:t:r')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-t':
            timeslot = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        else:
            usage()
                
    calldispatcher = CallEventDispatcher()
    
    c = Call(controller, calldispatcher, port=port, timeslot=timeslot)

    calldispatcher.run()

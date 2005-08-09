#!/usr/bin/env python

import sys
import getopt
import logging
import aculab
from aculab.snapshot import Snapshot
from aculab.error import AculabError
from aculab.callcontrol import *

class IncomingCallController:

    def ev_incoming_call_det(self, call, model):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)

        call.accept()

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, model):
        call.openin()

def usage():
    print 'usage: callin.py [-n <numcalls>] [-c <card> ] [-p <port>] [-t <timeslot>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    aculab.defaultLogging(logging.DEBUG)

    card = 0
    port = 0
    timeslot = None
    numcalls = 1
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'n:c:p:t:r?')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-p':
            port = int(a)
        elif o == '-n':
            numcalls = int(a)
        elif o == '-t':
            timeslot = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        else:
            usage()

    snapshot = Snapshot()

    print snapshot.call[card].ports[port].info.sig_sys
    print snapshot.call[card].ports[port].info.fw_desc
                
    port = snapshot.call[card].ports[port].open.port_id

    for i in range(numcalls):
        c = Call(controller, port=port, timeslot=timeslot)

    CallDispatcher.run()

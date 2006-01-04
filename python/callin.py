#!/usr/bin/env python

import sys
import getopt
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import *
import aculab.lowlevel as ll

class IncomingCallController:

    def ev_incoming_call_det(self, call, model):
        log.debug('%s stream: %d timeslot: %d: features: %d',
                  call.name, call.details.stream, call.details.ts,
                  call.details.feature_information)

        log.debug('HLC: %s',
                  repr(call.details.unique_xparms.sig_q931.hilayer.ie));

        if call.details.feature_information & ll.FEATURE_RAW_DATA:
            call.get_feature_details(ll.FEATURE_RAW_DATA)
            log.debug('raw data: %s',
                      repr(call.feature_details.feature.raw_data.getdata()))
        
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

    for i in range(numcalls):
        c = Call(controller, card=card, port=port, timeslot=timeslot)

    CallDispatcher.run()

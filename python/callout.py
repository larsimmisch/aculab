#!/usr/bin/env python

import sys
import getopt
import struct
import time
from aculab.error import AculabError
from aculab.callcontrol import *

OAD = '0403172541'

class Statistics:
    def __init__(self):
        self.min = None
        self.max = None
        self.average = 0.0
        self.count = 0

    def add(self, value):
        if self.min is None or value < self.min:
            self.min = value
        if self.max is None or value > self.max:
            self.max = value
        self.count = self.count + 1
        self.average = self.average + value

    def __repr__(self):
        return 'min: %f max: %f average: %f count: %d' % \
               (self.min, self.max, self.average / self.count, self.count)


statistics = Statistics()

class CallData:
    def __init__(self, number):
        self.number = number
        self.start = time.time()

    def start(self):
        self.start = time.time()

    def stop(self):
        statistics.add(time.time() - self.start)

class OutgoingCallController:

    def ev_outgoing_ringing(self, call, model):
        log.debug('%s stream: %d timeslot: %d', call.name,
                  call.details.stream, call.details.ts)

    def ev_call_connected(self, call, model):
        model.stop()
        log.info(statistics)

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

class RepeatedOutgoingCallController(OutgoingCallController):

    def ev_idle(self, call, model):
        call.user_data = CallData(model.number)
        call.openout(model.number, True, OAD)

def usage():
    print 'callout.py [-n <number of calls>] [-p <port>] [-c <card>] [-r] number'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    card = 0
    numcalls = 1
    timeslot = None

    log = aculab.defaultLogging(logging.DEBUG)

    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'c:p:rt:n:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-c':
            card = int(a)
        elif o == '-r':
            controller = RepeatedOutgoingCallController()
        elif o == '-t':
            timeslot = int(a)
        elif o == '-n':
            numcalls = int(a)
        else:
            usage()

    if not len(args):
        usage()

    fd = lowlevel.FEATURE_UNION()

    fd.uui.command = lowlevel.UU_DATA_CMD
    fd.uui.request = lowlevel.UUS_1_IMPLICITLY_PREFERRED
    fd.uui.control = lowlevel.CONTROL_NEXT_CC_MESSAGE
    fd.uui.protocol = lowlevel.UUI_PROTOCOL_USER_SPECIFIC
    fd.uui.setdata('Hallo Hauke, dies ist ein langer und entsetzliche langweiliger Text, den ich nur zum Testen von UUI benutze')

##     fd.raw_data.length = 6
##     fd.raw_data.data = struct.pack('BBBBBB',
##                                    2, # See Appendix M, Aculab Call Control
##                                    0x9f, 0x01, 0x02, 0x0a, 0x0b)

    unique = lowlevel.UNIQUEXU()
    unique.sig_q931.hilayer.ie = '\x02\x11\x01'
    
    for i in range(numcalls):
        c = Call(controller,  port=port, timeslot=timeslot)
        c.user_data = CallData(args[0])
##        c.openout(args[0], True, OAD)
        c.openout(args[0], 1, OAD,
                  unique = unique,
                  feature = lowlevel.FEATURE_USER_USER,
                  feature_data = fd)

##         fd.raw_data.length = 6
##         fd.raw_data.data = struct.pack('BBBBBB',
##                                        2, # See Appendix M, Aculab Call Control
##                                        0x9f, 0x01, 0x02, 0, 0)

##         c.feature_send(lowlevel.FEATURE_RAW_DATA,
##                        lowlevel.CONTROL_LAST_INFO_SETUP, fd)

    try:
        CallDispatcher.run()
    except KeyboardInterrupt:
        log.info(statistics)
        raise

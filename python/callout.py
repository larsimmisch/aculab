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
    print 'callout.py [-u] [-n <number of calls>] [-p <port>] [-c <card>] [-r] number'
    sys.exit(-2)

def build_cug(oa_request, cug_index):
    fd = lowlevel.FEATURE_UNION()
    fd.facility.length = 0x13
    fd.facility.data = struct.pack('21B', 0x1C, 0x13, 0x91, 0xA1, 0x10, 2, 2,
                                   0x8E, 0x10, 2, 1, 2, 0x30, 7, 0x81, 1,
                                   oa_request, 0x82, 2,
                                   (cug_index >> 8) & 0xff ,
                                   cug_index & 0xff)

    return fd

def build_cgpty_cat():
    fd = lowlevel.FEATURE_UNION()
    fd.raw_data.length = 6
    fd.raw_data.data = struct.pack('BBBBBB',
                                   2, # See Appendix M, Aculab Call Control
                                   0x9f, 0x01, 0x02, 0x0a, 0x0b)

def build_uui():
    fd = lowlevel.FEATURE_UNION()
    fd.uui.command = lowlevel.UU_DATA_CMD
    fd.uui.request = lowlevel.UUS_1_IMPLICITLY_PREFERRED
    fd.uui.control = lowlevel.CONTROL_NEXT_CC_MESSAGE
    fd.uui.protocol = lowlevel.UUI_PROTOCOL_USER_SPECIFIC
    fd.uui.setdata('Hallo Hauke, dies ist ein langer und entsetzliche langweiliger Text, den ich nur zum Testen von UUI benutze')

if __name__ == '__main__':
    port = 0
    card = 0
    numcalls = 1
    uui = False
    cug = False
    timeslot = None

    log = aculab.defaultLogging(logging.DEBUG)

    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'c:p:rt:n:uo:')

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
        elif o == '-u':
            uui = True
        elif o == '-g':
            cug = True
        elif o == '-o':
            OAD = a
        else:
            usage()

    if not len(args):
        usage()

    for i in range(numcalls):
        c = Call(controller,  port=port, timeslot=timeslot)
        c.user_data = CallData(args[0])
        if uui:
            c.openout(args[0], 1, OAD,
                      feature = lowlevel.FEATURE_USER_USER,
                      feature_data = build_uui())
        elif cug:
            c.openout(args[0], 1, OAD,
                      feature = lowlevel.FEATURE_FACILITY,
                      feature_data = build_cug(1, 2))
        else:
            c.openout(args[0], True, OAD)

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

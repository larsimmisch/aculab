#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import sys
import getopt
import struct
import time
import random
from aculab.error import AculabError
from aculab.reactor import CallReactor
from aculab.callcontrol import *
from aculab.timer import *

calling = '0403172541'
called = []

def get_called_number():
    if len(called) == 1:
        return called[0]
    else:
        return random.choice(called)

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
        if self.count:
            return 'min: %f max: %s average: %f count: %d' % \
                   (self.min, self.max, self.average / self.count, self.count)
        else:
            return 'min: %f max: %f average: n/a count: %d' % \
                   (self.min, self.max, self.count)

statistics = Statistics()

class CallData:
    def __init__(self):
        self.start = time.time()

    def start(self):
        self.start = time.time()

    def stop(self):
        statistics.add(time.time() - self.start)

class OutgoingCallController:

    def ev_wait_for_outgoing(self, call, user_data):
        call.user_data = CallData()

    def ev_outgoing_ringing(self, call, user_data):
        log.debug('%s stream: %d timeslot: %d', call.name,
                  call.details.stream, call.details.ts)

    def ev_call_connected(self, call, user_data):
        if hangup is not None:
            tt.add(hangup, call.disconnect)
        user_data.stop()
        log.info(statistics)

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        raise StopIteration

class RepeatedOutgoingCallController(OutgoingCallController):

    def ev_idle(self, call, user_data):
        call.openout(get_called_number(), True, calling)

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

def read_called_numbers(fname):
    f = open(fname, 'r')
    for l in f.readlines():
        l = l.strip()
        if l and l[0] != '#':
            called.append(l)

def usage():
    print 'callout.py [-u] [-n <number of calls>] [-p <port>] [-c <card>] [-r] [-h <hangup secs>] { number | -l <numbers in a file> }'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    card = 0
    numcalls = 1
    uui = False
    cug = False
    timeslot = None
    hangup = None

    log = aculab.defaultLogging(logging.DEBUG)

    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'c:h:l:p:rt:n:uo:')

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
        elif o == '-h':
            hangup = int(a)
            tt = TimerThread()
            tt.start()
        elif o == '-l':
            read_called_numbers(a)
        elif o == '-o':
            calling = a
        else:
            usage()

    if not len(args) and not called:
        usage()

    if not called:
        called.append(args[0])

    for i in range(numcalls):
        c = Call(controller, card=card, port=port, timeslot=timeslot)
        c.user_data = CallData()
        if uui:
            c.openout(get_called_number(), 1, calling,
                      feature = lowlevel.FEATURE_USER_USER,
                      feature_data = build_uui())
        elif cug:
            c.openout(get_called_number(), 1, calling,
                      feature = lowlevel.FEATURE_FACILITY,
                      feature_data = build_cug(1, 2))
        else:
            c.openout(get_called_number(), True, calling)

##         fd.raw_data.length = 6
##         fd.raw_data.data = struct.pack('BBBBBB',
##                                        2, # See Appendix M, Aculab Call Control
##                                        0x9f, 0x01, 0x02, 0, 0)

##         c.feature_send(lowlevel.FEATURE_RAW_DATA,
##                        lowlevel.CONTROL_LAST_INFO_SETUP, fd)

    try:
        CallReactor.run()
    except KeyboardInterrupt:
        log.info(statistics)
        raise

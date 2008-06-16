#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import sys
import struct
import time
import random
from aculab import defaultLogging, defaultOptions
from aculab.error import AculabError
from aculab.reactor import Reactor
from aculab.callcontrol import *
from aculab.timer import *

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
            return 'count: %d min: %.3f max: %.3f avg: %.3f' % \
                   (self.count, self.min, self.max, self.average / self.count)
        else:
            return 'count: 0 min: n/a max: n/a avg: n/a'

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
        if options.t_ringing is not None:
            tt.add(t_ringing, call.disconnect)
        log.debug('%s stream: %d timeslot: %d', call.name,
                  call.details.stream, call.details.ts)

    def ev_call_connected(self, call, user_data):
        if options.t_hangup is not None:
            tt.add(options.t_hangup, call.disconnect)
        user_data.stop()
        log.info(statistics)

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        if options.repeat:
            call.openout(get_called_number(), True, options.oad)
        else:
            raise StopIteration

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


def read_called_numbers(option, opt, value, parser):
    f = open(value, 'r')
    for l in f.readlines():
        l = l.strip()
        if l and l[0] != '#':
            called.append(l)
    f.close()

if __name__ == '__main__':

    parser = defaultOptions(
        usage='usage: %prog [options] <number>',
        description='Make outgoing PSTN call(s).',
        repeat=True)

    parser.add_option('-s', '--timeslot', type='int',
                      help='Use TIMESLOT for outgoing call.')

    parser.add_option('-n', '--numcalls', type='int', default=1,
                      help='Process NUMCALLS calls in parallel.')

    parser.add_option('-u', '--uui', action='store_true', 
                      help='Send ISDN UUI Type 1.')

    parser.add_option('-g', '--cug', action='store_true', 
                      help='Send ISDN Closed User Group.')

    parser.add_option('-w', '--t-ringing', type='int', 
                      help='Disconnect x seconds after receiving outgoing ' \
                      'ringing.')

    parser.add_option('-x', '--t-hangup', type='int', 
                      help='Disconnect x seconds after being connected.')

    parser.add_option('-l', '--numbers', type='string', action='callback',
                      callback=read_called_numbers,
                      help='Read the called party numbers from NUMBERS.')

    parser.add_option('-o', '--oad', default='403172541',
                      help='Use OAD as the originating address. ' \
                      'Default is 403172541.')

    options, args = parser.parse_args()

    if not args and not called:
        parser.print_help()
        sys.exit(2)

    # Only be verbose for two calls or less
    if options.numcalls <= 2:
        log = aculab.defaultLogging(logging.DEBUG)
    else:
        log = aculab.defaultLogging(logging.INFO)


    if options.t_ringing or options.t_hangup:
        tt = TimerThread()
        tt.start()    

    if not called:
        called.append(args[0])

    controller = OutgoingCallController()

    for i in range(options.numcalls):
        c = Call(controller, card=options.card, port=options.port,
                 timeslot=options.timeslot)
        
        c.user_data = CallData()
        if options.uui:
            c.openout(get_called_number(), 1, options.oad,
                      feature = lowlevel.FEATURE_USER_USER,
                      feature_data = build_uui())
        elif options.cug:
            c.openout(get_called_number(), 1, options.oad,
                      feature = lowlevel.FEATURE_FACILITY,
                      feature_data = build_cug(1, 2))
        else:
            c.openout(get_called_number(), True, options.oad)

##         fd.raw_data.length = 6
##         fd.raw_data.data = struct.pack('BBBBBB',
##                                        2, # See Appendix M, Aculab Call Control
##                                        0x9f, 0x01, 0x02, 0, 0)

##         c.feature_send(lowlevel.FEATURE_RAW_DATA,
##                        lowlevel.CONTROL_LAST_INFO_SETUP, fd)

    try:
        Reactor.run()
    except KeyboardInterrupt:
        log.info(statistics)
    except StopIteration:
        log.info(statistics)

#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import sys
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import *
from aculab.reactor import CallReactor
import aculab.lowlevel as ll

def hex_string(s):
    l = [hex(ord(c)) for c in s]
    return ' '.join(l)

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

        if call.details.feature_information == lowlevel.FEATURE_FACILITY:
            call.get_feature_details(ll.FEATURE_FACILITY)
            log.debug('%s Facility: %s', call.name,
                      hex_string(call.feature_details.feature.facility.getdata()))
        
        call.accept()

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

    def ev_idle(self, call, model):
        if options.repeat:
            call.openin()
        else:
            raise StopIteration
        
if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    parser = aculab.defaultOptions(
        description='Wait for and accept an incoming call.\n' \
        'The options -s and -n conflict and can not be used at the same time',
        repeat=True)

    parser.add_option('-s', '--timeslot', action='store', type='int',
                      default = None, help='Timeslot to use.')
    parser.add_option('-n', '--numcalls', action='store', type='int',
                      default = 1, help='Calls to open')

    options, args = parser.parse_args()

    if options.timeslot is not None and options.numcalls:
        print parser.print_help()
        sys.exit(2)
        
    controller = IncomingCallController()

    for i in range(options.numcalls):
        c = Call(controller, card=options.card, port=options.port,
                 timeslot=options.timeslot)

    try:
        CallReactor.run()
    except StopIteration:
        pass
    

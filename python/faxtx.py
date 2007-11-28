#!/usr/bin/env python

# Copyright (C) 2004-2007 Lars Immisch

import sys
import os
import threading
import logging
import struct
import time
import aculab
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel, Glue
from aculab.reactor import CallReactor, SpeechReactor
from aculab.switching import DefaultBus

class OutgoingCallController:

    def ev_wait_for_outgoing(self, call, user_data):
        pass

    def ev_outgoing_ringing(self, call, user_data):
        call.user_data = Glue(self, options.module, call)

    def ev_call_connected(self, call, user_data):
        user_data.speech.faxtx('diversion_1.tif')
        
    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        raise StopIteration

    def faxtx_done(self, channel, reason, user_data):
        call.disconnect()

    def digits_done(self, channel, user_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        pass

if __name__ == '__main__':

    parser = aculab.defaultOptions(
        usage='usage: %prog [options] <number>',
        description = 'Send a T.30 FAX to <number>.')
    options, args = parser.parse_args()

    if not args:
        print parser.print_help()
        sys.exit(2)

    number = args[0]

    log = aculab.defaultLogging(logging.DEBUG)
    controller = OutgoingCallController()
    call = Call(controller, card=options.card, port=options.port)

    call.openout(number, True)

    try:
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass

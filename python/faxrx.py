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
from aculab.reactor import Reactor
from aculab.switching import DefaultBus

class IncomingCallController:

    def ev_incoming_call_det(self, call, user_data):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)
        
        # The Prosody module that was globally selected.
        # Proper applications that handle multiple modules 
        # can be more clever here
        call.user_data = Glue(self, module, call)        
        call.accept()

    def ev_call_connected(self, call, user_data):
        user_data.speech.faxrx('test.tif', '0403172541')
        
    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        call.user_data = None

    def faxrx_done(self, channel, reason, user_data, job_data):
        call.disconnect()

    def digits_done(self, channel, user_data, job_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        print 'got DTMF:', digit

    def ev_idle(self, call, user_data):
        if options.repeat:
            call.openin()
        else:
            raise StopIteration

if __name__ == '__main__':

    parser = aculab.defaultOptions(description='Receive a T.30 FAX.',
                                   repeat=True)
    options, args = parser.parse_args()

    log = aculab.defaultLogging(logging.DEBUG)

    controller = IncomingCallController()

    call = Call(controller, card=options.card, port=options.port)

    Reactor.run()

#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import struct
import time
import aculab
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.callcontrol import Call, CallDispatcher
from aculab.speech import SpeechChannel, SpeechDispatcher, Glue
from aculab.busses import DefaultBus

class IncomingCallController:

    def ev_incoming_call_det(self, call, user_data):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)
        
        # The Prosody module that was globally selected.
        # Proper applications that handle multiple modules 
        # can be more clever here
        global module
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

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        call.openin()

def usage():
    print 'usage: faxrx.py [-c <card>] [-p <port>] [-m <module>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    card = 0
    port = 0
    module = 0
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:rsm:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        if o == '-p':
            port = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        elif o == '-s':
            DefaultBus = SCBus()
        else:
            usage()

    snapshot = Snapshot()
    port = snapshot.call[card].ports[port].open.port_id

    call = Call(controller, port=port)

    SpeechDispatcher.start()
    CallDispatcher.run()

#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call, CallEventDispatcher
from aculab.speech import SpeechChannel, SpeechEventDispatcher
from aculab.busses import DefaultBus

class AnsweringMachine:

    def __init__(self, call = None, speech = None, connection = None):
        self.mutex = threading.RLock()
        self.call = call
        self.speech = speech
        self.connection = connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.speech:
            self.speech.close()
            self.speech = None

class IncomingCallController:

    def ev_incoming_call_det(self, call, model):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)

        speech = SpeechChannel(self, speechdispatcher, 0)

        call.user_data = AnsweringMachine(call, speech,
                                          call.connect(speech))

        call.accept()

    def ev_call_connected(self, call, model):        
        model.speech.play('greeting.al')
        # model.digits('123456')
        # model.record('recording.al', 90000)
        
    def ev_remote_disconnect(self, call, model):
        call.disconnect()

    def ev_idle(self, call, model):
        model.close()
        call.user_data = None

    def play_done(self, channel, reason, position, model):
        pass

    def record_done(self, channel, reason, position, model):
        pass
    
    def digits_done(self, channel, model):
        pass
    
    def dtmf(self, channel, digit, model):
        print 'got DTMF:', digit

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, model):
        call.openin()

def usage():
    print 'usage: am.py [-p <port>] [-m <module>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    port = 0
    module = 0
    controller = IncomingCallController()

    bus = DefaultBus

    options, args = getopt.getopt(sys.argv[1:], 'p:rsm:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        elif o == '-s':
            bus = SCBus()
        else:
            usage()

    if not bus:
        bus = H100()

    speechdispatcher = SpeechEventDispatcher()
    calldispatcher = CallEventDispatcher()

    call = Call(controller, calldispatcher, port)

    speechdispatcher.start()
    calldispatcher.run()

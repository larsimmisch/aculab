#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call, CallDispatcher
from aculab.speech import SpeechChannel, SpeechDispatcher
from aculab.busses import DefaultBus

class AnsweringMachine:

    def __init__(self, call = None, speech = None, connection = None):
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

    def ev_incoming_call_det(self, call, user_data):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)

        global module
        speech = SpeechChannel(self, module, user_data=user_data)

        call.user_data = AnsweringMachine(call, speech,
                                          call.connect(speech))

        call.accept()

    def ev_call_connected(self, call, user_data):        
        user_data.speech.play('greeting.al')
        
    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        call.user_data = None

    def play_done(self, f, channel, reason, position, job_data):
        t = os.tmpfile()
        channel.record(t, 90000)

    def record_done(self, f, channel, reason, position, job_data):
        f.close()
    
    def digits_done(self, channel, user_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        print 'got DTMF:', digit

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        call.openin()

def usage():
    print 'usage: am.py [-p <port>] [-m <module>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    port = 0
    module = 0
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:rsm:')

    for o, a in options:
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

    call = Call(controller, port)

    SpeechDispatcher.start()
    CallDispatcher.run()

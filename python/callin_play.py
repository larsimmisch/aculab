#!/usr/bin/env python

import sys
import os
import getopt
import threading
from aculab.error import AculabError
from aculab.callcontrol import Call, CallEventDispatcher
from aculab.speech import SpeechChannel, SpeechEventDispatcher
from aculab.busses import autodetect

class IncomingCallController:

    def __init__(self):
        self.mutex = threading.Lock()

    def ev_incoming_call_det(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

        call.accept()

    def ev_call_connected(self, call):
        call.speech = SpeechChannel(self, speechdispatcher, 0)
        call.connection = call.connect(call.speech)
        
        # call.speech.play('../../menu.al')
        call.speech.digits('123456')
        # call.speech.record('recording.al', 90000)
        
    def ev_remote_disconnect(self, call):
        call.speech.stop()
        call.connection.close()
        call.connection = None
        call.speech.release()
        call.speech = None
        call.disconnect()

    def play_done(self, channel, position, user_data):
        print 'play done. position:', position

    def record_done(self, channel, how, position, user_data):
        print 'record done. position: %d how: %d' % (position, how)

    def digits_done(self, channel, user_data):
        print 'digits done'

    def dtmf(self, channel, digit):
        print 'got DTMF:', digit

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call):
        call.openin()

def usage():
    print 'usage: callin.py [-p <port>] [-m <module>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    port = 0
    module = 0
    controller = IncomingCallController()

    bus = autodetect()

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

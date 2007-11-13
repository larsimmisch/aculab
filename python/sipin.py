#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.switching import connect
from aculab.sip import SIPCall
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP

class CallData:
    
    def __init__(self, controller, call):
        self.call = call
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.speech = SpeechChannel(controller, user_data=self)
        self.connection = None

    def connect(self):
        self.connection = connect((self.vmptx, self.vmprx), self.speech)
        
    def close(self):
        for attr in ['connection', 'call', 'speech', 'vmprx', 'vmptx']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class IncomingCallController:

    def vmprx_ready(self, vmprx, sdp, user_data):
        """Called when the vmprx is ready."""
        vmprx.config_tones(True, True)
        user_data.call.accept(sdp)

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

    def ev_incoming_call_det(self, call, user_data):
        call.user_data = CallData(self, call)
        
        sdp = SDP(call.details.media_offer_answer.raw_sdp)

        log.debug('got SDP: %s', sdp)
        
        call.user_data.vmptx.configure(sdp)

        call.incoming_ringing()

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        user_data.speech.play('asteria.al')
        
    def play_done(self, channel, f, reason, position, user_data):
        # The call might be gone already
        if user_data.call:
            user_data.call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        raise StopIteration
        
class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        user_data.close()
        call.openin()

def usage():
    print '''usage: sipin.py [-n <numcalls>] [-r]'''
    sys.exit(-2)

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    numcalls = 1
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'nr?')

    for o, a in options:
        if o == '-n':
            numcalls = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        else:
            usage()

    for i in range(numcalls):
        c = SIPCall(controller)

    try:
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass


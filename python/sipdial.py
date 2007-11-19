#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

# This example accepts an incoming SIP call and makes an outgoing call
# with no called party number. As DTMF digits come on via the SIP leg,
# the digits are sent out as overlap digits on the ISDN leg.

# Written for Dima to simulate the behaviour of a PBX

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.callcontrol import CallHandle
from aculab.switching import connect
from aculab.sip import SIPCall
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP

class CallData:
    
    def __init__(self, controller, call):
        self.outcall = None
        self.incall = call
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.speech = SpeechChannel(controller, user_data=self)
        self.connection = None

    def connect(self):
        self.connection = connect((self.vmptx, self.vmprx), self.speech)
        
    def close(self):
        for attr in ['connection', 'incall', 'outcall', 'speech',
                     'vmprx', 'vmptx']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class IncomingCallController:

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""
        vmprx.config_tones()
        sd = vmprx.default_codec(True)
        user_data.incall.accept(sd)

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
        if call == user_data.outcall:
            user_data.incall.disconnect()
        else:
            user_data.outcall.disconnect()

    def ev_media(self, call, user_data):
        sd = SDP(call.details.media_session.received_media.raw_sdp)

        user_data.vmptx.configure(sd, user_data.vmprx.get_rtp_address())

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        user_data.outcall = CallHandle(self, user_data)
        user_data.outcall.openout('', False)

        # Dial tone, 400Hz
        user_data.speech.tone(9)
        
    def play_done(self, channel, reason, f, duration, user_data):
        # The call might be gone already
        if user_data.incall:
            user_data.incall.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        
class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        user_data.close()
        call.openin()

def usage():
    print '''usage: sipdial.py [-n <numcalls>] [-r]'''
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

    SpeechReactor.start()
    CallReactor.run()


#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.switching import connect
from aculab.sip import SIPHandle
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP

class CallData:
    
    def __init__(self, controller, number):
        # Create the call handle here, do the openout in ready
        self.number = number
        self.call = SIPHandle(controller, self)
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.speech = SpeechChannel(controller, user_data=self)
        self.connection = None

    def vmprx_ready(self, vmprx, sdp):
        self.call.openout(self.number, sdp)
        vmprx.config_tones()

    def ev_media(self, call):
        # The call has already received the details for us
        # and that's how we get at the SDP:
        sdp = SDP(call.details.media_session.received_media.raw_sdp)

        self.vmptx.configure(sdp)

    def connect(self):
        self.connection = connect((self.vmptx, self.vmprx), self.speech)

    def close(self):
        for attr in ['connection', 'call', 'speech', 'vmprx', 'vmptx']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class OutgoingCallController:

    def vmprx_ready(self, vmprx, sdp, user_data):
        """Called when the vmprx is ready."""
        user_data.vmprx_ready(vmprx, sdp)

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

    def ev_media(self, call, user_data):
        user_data.ev_media(call)

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
        
def usage():
    print '''usage: sipout.py [-n <numcalls>] <number>'''
    sys.exit(-2)

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    numcalls = 1
    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'n?')
    if not args:
        usage()

    for o, a in options:
        if o == '-n':
            numcalls = int(a)
        else:
            usage()

    for i in range(numcalls):
        c = CallData(controller, args[0])

    SpeechReactor.start()
    CallReactor.run()

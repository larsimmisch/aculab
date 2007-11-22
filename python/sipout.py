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

    def vmprx_ready(self, vmprx):
        self.our_sdp = vmprx.default_sdp()# (enable_rfc2833 = False)
        vmprx.configure(self.our_sdp)
        
        self.call.openout(self.number, self.our_sdp)
        vmprx.config_tones()

    def ev_media(self, call):
        # The call has already received the details for us
        # and that's how we get at the SDP:
        self.other_sdp = SDP(call.details.media_session.received_media.raw_sdp)

        self.other_sdp.intersect(self.our_sdp)

        self.vmptx.configure(self.other_sdp)
        self.vmptx.config_tones(False, False)

    def connect(self):
        self.connection = connect((self.vmptx, self.vmprx), self.speech)
        self.speech.listen_for()

        if fax:
            self.speech.tone(23, 1.0)
            # self.speech.faxtx(fax)
        else:
            self.speech.play('12345CNG.al')

    def close(self):
        for attr in ['connection', 'call', 'speech', 'vmprx', 'vmptx']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class OutgoingCallController:

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""
        user_data.vmprx_ready(vmprx)

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

    def ev_media(self, call, user_data):
        user_data.ev_media(call)

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        
    def play_done(self, channel, reason, f, duration, user_data):
        # The call might be gone already
        if user_data.call:
            user_data.call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        raise StopIteration
        
def usage():
    print '''usage: sipout.py [-n <numcalls>] <number>'''
    sys.exit(-2)

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    numcalls = 1
    fax = None
    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'n?f:')
    if not args:
        usage()

    for o, a in options:
        if o == '-n':
            numcalls = int(a)
        elif o == '-f':
            fax = a
        else:
            usage()

    for i in range(numcalls):
        c = CallData(controller, args[0])

    try:
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass

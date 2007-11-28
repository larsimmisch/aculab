#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import logging
from aculab import defaultLogging, defaultOptions
from aculab.lowlevel import cvar
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
        self.vmptx = VMPtx(controller, card=options.card,
                           module=options.module, user_data=self)
        self.vmprx = VMPrx(controller, card=options.card,
                           module=options.module, user_data=self)
        self.speech = SpeechChannel(controller, card=options.card,
                           module=options.module, user_data=self)
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

        if options.fax:
            # self.speech.tone(23, 1.0)
            self.speech.faxtx(options.fax)
        else:
            self.speech.listen_for()
            self.speech.play(options.file_name)

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
        
if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    parser = defaultOptions(
        usage='usage: %prog [options] <number>',
        description='Make an outgoing SIP call and play a prompt.')

    parser.add_option('-f', '--file-name', default='12345CNG.al',
                      help='Play FILE instead of 12345CNG.al')

    parser.add_option('-x', '--fax', 
                      help='Send Fax FILE instead of playing a prompt.')

    parser.add_option('-n', '--numcalls', type='int', default=1,
                      help='Process NUMCALLS calls in parallel.')

    options, args = parser.parse_args()

    if not args:
        parser.print_help()
        sys.exit(2)

    controller = OutgoingCallController()

    for i in range(options.numcalls):
        c = CallData(controller, args[0])

    try:
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass

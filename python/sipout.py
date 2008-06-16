#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import os
import logging
from aculab import defaultLogging, defaultOptions
from aculab.speech import SpeechChannel
from aculab.reactor import Reactor
from aculab.switching import connect, Connection
from aculab.sip import SIPHandle
from aculab.rtp import VMPrx, VMPtx
import aculab.sdp as sdp

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

        if options.video:
            md = sdp.MediaDescription('video 0 RTP/AVP')
            md.setLocalPort(0)
            md.addRtpMap(sdp.PT_H263)
            self.our_sdp.addMediaDescription(md)
        
        vmprx.configure(self.our_sdp)
        
        self.call.openout(self.number, self.our_sdp)
        vmprx.config_tones()

    def ev_media(self, call):
        # The call has already received the details for us
        # and that's how we get at the SDP:
        self.other_sdp = sdp.SDP(call.details.media_session.received_media.raw_sdp)

        self.other_sdp.intersect(self.our_sdp)

        # We need to do symmtric NAT for the Fritzbox
        self.vmptx.configure(self.other_sdp, self.vmprx.get_rtp_address())
        self.vmptx.config_tones(False, False)

    def connect(self):

        if options.fax:
            trace = os.path.splitext(options.fax)[0] + '.log'
            
            # self.speech.tone(23, 1.0)
            self.speech.faxtx(options.fax, 'sipout.py',
                              (self.vmptx, self.vmprx), trace)
        else:
            self.connection = connect((self.vmptx, self.vmprx), self.speech)
            
            self.speech.listen_for()
            self.speech.play(options.file_name)

    def close(self):
        if self.connection:
            self.connection.close()
        self.speech.close(self.vmprx, self.vmptx)
        # set all resources to None
        self.speech = self.connection = self.call = None
        self.vmprx = self.vmptx = None

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
        if options.repeat:
            CallData(self, args[0])
        else:
            raise StopIteration
                     
if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    parser = defaultOptions(True,
        usage='usage: %prog [options] <number>',
        description='Make an outgoing SIP call and play a prompt.')

    parser.add_option('-f', '--file-name', default='12345CNG.al',
                      help='Play FILE instead of 12345CNG.al')

    parser.add_option('-x', '--fax', 
                      help='Send Fax FILE_NAME instead of playing a prompt.')

    parser.add_option('-n', '--numcalls', type='int', default=1,
                      help='Process NUMCALLS calls in parallel.')

    parser.add_option('-v', '--video', action='store_true', default=False,
                      help='Add a video codec (test only).')

    options, args = parser.parse_args()

    if not args:
        parser.print_help()
        sys.exit(2)

    controller = OutgoingCallController()

    for i in range(options.numcalls):
        CallData(controller, args[0])

    try:
        Reactor.run()
    except StopIteration:
        pass

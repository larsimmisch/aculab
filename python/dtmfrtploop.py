#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

# Connect a VMPrx/VMPtx pair over IP, and play/detect DTMF on connect
# Prosody Channels

import logging
import aculab.lowlevel as lowlevel
import aculab
from aculab.error import AculabError
from aculab.speech import SpeechChannel
from aculab.rtp import VMPtx, VMPrx
from aculab.reactor import SpeechReactor
from aculab.switching import connect

class RTPLoop:
    def __init__(self, controller, card, module):
        self.vmptx = VMPtx(controller, card, module, user_data=self)
        self.vmprx = VMPrx(controller, card, module, user_data=self)
        self.speechrx = SpeechChannel(controller, card, module, user_data=self)
        self.speechtx = SpeechChannel(controller, card, module, user_data=self)

        self.speechrx.listen_for('dtmf/fax', options.mode)

        self.connections = [self.speechrx.listen_to(self.vmprx),
                            self.vmptx.listen_to(self.speechtx)]

class RTPLoopController:

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""

        sd = vmprx.default_sdp(configure=True)
        
        log.debug('vmprx SDP: %s', sd)
        user_data.vmptx.configure(sd)

        # convert: regenerate, eliminate: False
        user_data.vmptx.config_tones(options.regenerate, False)

        # detect: True, regen: False
        user_data.vmprx.config_tones(True, False)

        if options.file_name:
            user_data.speechtx.play(options.file_name)
        else:
            user_data.speechtx.digits('0123456789*#')
            
        user_data.speechrx.record('dtmfrtp.al', max_silence = 1.0)

    def vmprx_newssrc(self, vmprx, address, ssrc, user_data):
        pass

    def dtmf(self, channel, digit, user_data):
        pass

    def play_done(self, channel, reason, f, duration, user_data):
        raise StopIteration

    def record_done(self, channel, file, reason, size, user_data):
        pass
    
    def digits_done(self, channel, reason, user_data):
        channel.tone(23, 1.0)

    def tone_done(self, channel, reason, user_data):
        channel.silence(1.0)

    def silence_done(self, channel, reason, duration, user_data):
        raise StopIteration    
        
if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    parser = aculab.defaultOptions(
        description='Detect DTMF and CNG on a VMPrx/VMPtx pair connected '\
        'via RTP.')

    parser.add_option('-l', '--lendetect', action='store_const', dest='mode',
                      default=lowlevel.kSMToneDetectionMinDuration64,
                      const=lowlevel.kSMToneLenDetectionMinDuration64,
                      help='Use kSMToneLenDetectionMinDuration64 for the' \
                      'tone detection mode.')

    parser.add_option('-r', '--regenerate', action='store_const',
                      default=0, const=1,
                      help='On the VMPtx, regenerate DTMF from RFC2833.')

    parser.add_option('-f', '--file-name', 
                      help='Play FILE instead of sending 0123456789*#')

    options, args = parser.parse_args()

    controller = RTPLoopController()
    loop = RTPLoop(controller, options.card, options.module)

    SpeechReactor.run()

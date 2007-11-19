#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

# Connect a VMPrx/VMPtx pair over IP, and play/detect DTMF on connect
# Prosody Channels

import sys
import os
import getopt
import threading
import logging
import struct
import time
import traceback
import aculab.lowlevel as lowlevel
from aculab import defaultLogging
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

        self.speechrx.listen_for('dtmf/fax', mode)

        self.connections = [self.speechrx.listen_to(self.vmprx),
                            self.vmptx.listen_to(self.speechtx)]

class RTPLoopController:

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""

        sd = vmprx.default_sdp(configure=True)
        
        log.debug('vmprx SDP: %s', sd)
        user_data.vmptx.configure(sd)

        # convert: regenerate, eliminate: False
        user_data.vmptx.config_tones(regenerate, False)

        # detect: True, regen: False
        user_data.vmprx.config_tones(True, False)

        if fname:
            user_data.speechtx.play(fname)
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
        
def usage():
    print '''usage: dtmfrtploop.py [-c <card>] [-m <module>] [-t <tingtrace>]
    -l turns on digit recognition via kSMToneLenDetectionMinDuration64

    If -f is given, <file> is played. If no file is specified,
    0123456789*# plus CNG is generated.
    '''
    sys.exit(-2)

if __name__ == '__main__':

    log = defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = RTPLoopController()
    regenerate = False
    fname = None
    mode = lowlevel.kSMToneDetectionMinDuration64

    options, args = getopt.getopt(sys.argv[1:], 'c:m:t:f:rlh?')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-t':
            aculab.lowlevel.cvar.TiNGtrace = int(a)
        elif o == '-f':
            fname = a            
        elif o == '-r':
            regenerate = True
        elif o == '-l':
            mode = lowlevel.kSMToneLenDetectionMinDuration64
        else:
            usage()

    loop = RTPLoop(controller, card, module)

    SpeechReactor.run()

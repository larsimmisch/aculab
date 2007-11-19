#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

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
from aculab.reactor import SpeechReactor
from aculab.switching import connect

class DTMFLoopController:

    def dtmf(self, channel, digit, user_data):
        pass

    def record_done(self, channel, file, reason, size, user_data):
        pass

    def play_done(self, channel, reason, f, duration, user_data):
        raise StopIteration
                
    def digits_done(self, channel, reason, user_data):
        # Play a CNG
        channel.tone(23, 1.0)

    def tone_done(self, channel, reason, user_data):
        # Give the CNG detector some time
        channel.silence(1.0)

    def silence_done(self, channel, reason, duration, user_data):
        raise StopIteration

def usage():
    print '''usage: dtmfloop.py [-c <card>] [-m <module>] [-t <tingtrace>] \\
    [-l] [ -f <file>]

    -l selects kSMToneLenDetectionMinDuration64 as tone detection mode (note
    the Len)

    If -f is given, <file> is played. If no file is specified,
    0123456789*# plus CNG is generated.
    '''
    sys.exit(-2)

if __name__ == '__main__':

    log = defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = DTMFLoopController()
    mode = lowlevel.kSMToneDetectionMinDuration64
    fname = None

    options, args = getopt.getopt(sys.argv[1:], 'c:m:t:f:lh?')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-t':
            aculab.lowlevel.cvar.TiNGtrace = int(a)
        elif o == '-f':
            fname = a
        elif o == '-l':
            mode = lowlevel.kSMToneLenDetectionMinDuration64
        else:
            usage()

    channels = [SpeechChannel(controller, card, module),
                SpeechChannel(controller, card, module)]

    connection = connect(channels[0], channels[1])

    channels[0].listen_for('dtmf/fax', mode)
    
    channels[0].record('dtmf.al', max_silence = 1.0)
    if fname:
        channels[1].play(fname)
    else:
        channels[1].digits('0123456789*#')

    SpeechReactor.run()

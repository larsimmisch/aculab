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
from aculab import defaultLogging
from aculab.error import AculabError
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor
from aculab.switching import connect

class DTMFLoopController:

    def dtmf(self, channel, digit, user_data):
        log.info('%s dtmf: %s', channel.name, digit)

    def record_done(self, channel, file, reason, size, user_data):
        pass

    def digits_done(self, channel, reason, user_data):
        channel.tone(23, 1000)

    def tone_done(self, channel, reason, user_data):
        raise StopIteration

def usage():
    print 'usage: dtmfloop.py [-c <card>] [-m <module>] [-t <tingtrace>]'
    sys.exit(-2)

if __name__ == '__main__':

    log = defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = DTMFLoopController()

    options, args = getopt.getopt(sys.argv[1:], 'c:m:t:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-t':
            aculab.lowlevel.cvar.TiNGtrace = int(a)
        else:
            usage()

    channels = [SpeechChannel(controller, card, module),
                SpeechChannel(controller, card, module)]

    connection = connect(channels[0], channels[1])

    channels[0].listen_for('dtmf/fax')
    channels[0].record('dtmf.al', max_silence = 1000)
    channels[1].digits('0123456789*#')
    
    SpeechReactor.run()

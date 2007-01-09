#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import struct
import time
import aculab
import traceback
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.speech import SpeechChannel, SpeechDispatcher, Glue
from aculab.busses import DefaultBus

class DTMFLoopController:

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

    def record_done(self, channel, file, reason, size, user_data):
        raise StopIteration

    def digits_done(self, channel, reason, user_data):
        raise StopIteration

def usage():
    print 'usage: dtmfloop.py [-c <card>] [-m <module>] [-t <tingtrace>]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

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

    snapshot = Snapshot()

    channels = [SpeechChannel(controller, card, module),
                SpeechChannel(controller, card, module)]

    connection = channels[0].connect(channels[1])

    for i in (0, 1):
        log.debug("[%d] %d:%d", i, channels[i].info.ost, channels[i].info.ots)

    channels[0].record('dtmf.al', max_silence = 1000)
    channels[1].digits('1234567890')
    
    SpeechDispatcher.run()

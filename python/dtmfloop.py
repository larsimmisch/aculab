#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import struct
import time
import aculab
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.speech import SpeechChannel, SpeechDispatcher, Glue
from aculab.busses import DefaultBus

class DTMFLoopController:

    def dtmf(self, channel, reason, user_data, job_data):
        pass

    def record_done(self, channel, file, reason, size, user_data, job_data):
        pass

    def digits_done(self, channel, reason, user_data, job_data):
        pass

def usage():
    print 'usage: dtmfloop.py [-c <card>] [-m <module>]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = DTMFLoopController()

    options, args = getopt.getopt(sys.argv[1:], 'c:m:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        else:
            usage()

    snapshot = Snapshot()

    channels = [SpeechChannel(controller, card, module),
                SpeechChannel(controller, card, module)]

    connection = channels[0].connect(channels[1])

    for i in (0, 1):
        print "[%d] %d:%d" % (i, channels[i].info.ost, channels[i].info.ots)

    channels[0].record('dtmf.al', max_silence = 1000)
    channels[1].digits('1234567890')
    
    SpeechDispatcher.run()

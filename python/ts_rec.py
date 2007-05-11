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

class RecordController:

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

    def record_done(self, channel, file, reason, size, user_data):
        raise StopIteration

def usage():
    print '''usage:
    dtmfloop.py [-c <card>] [-m <module>] <stream>:<timeslot> <filename>
    '''
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = RecordController()
    slot = None

    options, args = getopt.getopt(sys.argv[1:], 'c:m:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        else:
            usage()

    try:
        st = args[0].split(':')
        slot = (int(st[0]), int(st[1]))
        filename = args[1]
    except IndexError:
        usage()
        
    snapshot = Snapshot()

    channel = SpeechChannel(controller, card, module)

    channel.record(filename)
    con = channel.listen_to(slot)
    
    SpeechDispatcher.run()

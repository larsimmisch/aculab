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
from aculab.rtp import VMPtx, VMPrx
from aculab.reactor import SpeechReactor
from aculab.switching import connect

class RTPLoop:
    def __init__(self, controller, card, module):
        self.vmptx = VMPtx(controller, card, module, user_data=self)
        self.vmprx = VMPrx(controller, card, module, user_data=self)
        self.speechrx = SpeechChannel(controller, card, module, user_data=self)
        self.speechtx = SpeechChannel(controller, card, module, user_data=self)

        self.connections = [self.speechrx.listen_to(self.vmprx),
                            self.vmptx.listen_to(self.speechtx)]

class RTPLoopController:

    def vmprx_ready(self, vmprx, sdp, user_data):
        """Called when the vmprx is ready."""
        user_data.vmptx.configure(sdp)

        user_data.speechtx.digits('0123456789')

    def dtmf(self, channel, digit, user_data):
        log.info('%s dtmf: %s', channel.name, digit)

    def record_done(self, channel, file, reason, size, user_data):
        raise StopIteration

    def digits_done(self, channel, reason, user_data):
        raise StopIteration

def usage():
    print 'usage: dtmfrtploop.py [-c <card>] [-m <module>] [-t <tingtrace>]'
    sys.exit(-2)

if __name__ == '__main__':

    log = defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = RTPLoopController()

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

    loop = RTPLoop(controller, card, module)

    SpeechReactor.run()

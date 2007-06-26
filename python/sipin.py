#!/usr/bin/env python

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.error import AculabError
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.sip import SIPCall
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP

import aculab.lowlevel as ll

class CallData:
    
    def __init__(self, controller, call):
        self.call = call
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.channel = SpeechChannel(controller, user_data=self)
        self.connection = None

    def connect(self):
        self.connection = [self.vmptx.listen_to(self.channel),
                           self.channel.listen_to(self.vmprx)]

        self.channel.play('asteria.al')

class IncomingCallController:

    def ready(self, vmprx, sdp, user_data):
        """Called when the vmprx is ready."""
        user_data.call.accept(sdp)

    def ev_incoming_call_det(self, call, user_data):
        call.user_data = CallData(self, call)
        
        sdp = SDP(call.details.media_offer_answer.raw_sdp)

        log.debug('got SDP: %s', sdp)
        
        call.user_data.vmptx.configure(sdp)

        call.incoming_ringing()

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        
    def play_done(self, channel, f, reason, position, user_data):
        pass

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, model):
        call.openin()

def usage():
    print '''usage: sipin.py [-n <numcalls>] [-r]'''
    sys.exit(-2)

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    numcalls = 1
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'nr?')

    for o, a in options:
        if o == '-n':
            numcalls = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        else:
            usage()

    for i in range(numcalls):
        c = SIPCall(controller)

    SpeechReactor.start()
    CallReactor.run()

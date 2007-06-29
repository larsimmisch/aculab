#!/usr/bin/env python

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.busses import Connection
from aculab.sip import SIPCall
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP

class CallData:
    
    def __init__(self, controller, call):
        self.call = call
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.channel = SpeechChannel(controller, user_data=self)
        self.connection = None

    def connect(self):
        eps = [self.vmptx.listen_to(self.channel),
               self.channel.listen_to(self.vmprx)]

        self.connection = Connection(endpoints = eps)

    def close(self):
        self.connection.close()
        self.vmptx.close()
        self.vmprx.close()
        self.channel.close()
        self.call = None
        self.connection = None
        self.vmprx = None
        self.vmptx = None
        self.channel = None
    
class IncomingCallController:

    def ready(self, vmprx, sdp, user_data):
        """Called when the vmprx is ready."""
        vmprx.config_tones()
        user_data.call.accept(sdp)

    def dtmf(self, channel, digit, user_data):
        log.info('dtmf: %s', digit)

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
        user_data.channel.play('asteria.al')
        
    def play_done(self, channel, f, reason, position, user_data):
        # The call might be gone already
        if user_data.call:
            user_data.call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        
class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        user_data.close()
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


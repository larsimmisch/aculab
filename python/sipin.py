#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import getopt
import logging
from aculab import defaultLogging
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.switching import connect, Connection
from aculab.snapshot import Snapshot
from aculab.sip import SIPCall
from aculab.rtp import VMPrx, VMPtx
from aculab.sdp import SDP
from aculab.snapshot import Snapshot
from aculab.lowlevel import ACU_SIP_REGISTER_NOTIFICATION

class CallData:
    
    def __init__(self, controller, call, in_sd):
        self.call = call
        self.in_sd = in_sd
        self.vmptx = VMPtx(controller, user_data=self)
        self.vmprx = VMPrx(controller, user_data=self)
        self.speech = SpeechChannel(controller, user_data=self)
        self.connection = None

    def connect(self):
        #self.connection = connect((self.vmptx, self.vmprx), self.speech)

        self.connection = Connection(
            endpoints = [self.vmptx.listen_to(self.speech.get_timeslot()),
                         self.speech.listen_to(self.vmprx.get_timeslot())])

        #self.connection = Connection(
        #    endpoints = [self.speech.listen_to(self.vmprx.get_timeslot())])
        
    def close(self):
        for attr in ['connection', 'call', 'speech', 'vmprx', 'vmptx']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class IncomingCallController:

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""
        rx_sd = vmprx.default_sdp()
        rx_sd.intersect(user_data.in_sd)

        vmprx.configure(rx_sd)

        log.debug('sent SDP:\n%s', rx_sd)

        user_data.call.accept(rx_sd)

    def dtmf(self, channel, digit, user_data):
        # log.info('dtmf: %s', digit)
        pass

    def ev_incoming_call_det(self, call, user_data):
        sdp = SDP(call.details.media_offer_answer.raw_sdp)

        call.user_data = CallData(self, call, sdp)

        log.debug('got SDP:\n%s', sdp)

        call.incoming_ringing()

    def ev_media(self, call, user_data):
        # sdp = SDP(call.details.media_session.sent_media.raw_sdp)
        # log.debug('sent SDP:\n%s', sdp)

        sdp = SDP(call.details.media_session.received_media.raw_sdp)
        #log.debug('received SDP:\n%s', sdp)

        user_data.vmptx.configure(sdp, user_data.vmprx.get_rtp_address())

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        user_data.vmprx.config_tones(True, False)
        user_data.vmptx.config_tones(False, False)
        user_data.speech.listen_for('dtmf/fax')
        if not silent:
            user_data.speech.play('asteria.al')
        else:
            user_data.speech.record('sipin.al', max_silence = 5.0)
        
    def play_done(self, channel, reason, f, duration, user_data):
        # The call might be gone already
        if user_data.call:
            user_data.call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        raise StopIteration
        
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
    silent = False

    options, args = getopt.getopt(sys.argv[1:], 'nrs?')

    for o, a in options:
        if o == '-n':
            numcalls = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        elif o == '-s':
            silent = True
        else:
            usage()

    for i in range(numcalls):
        c = SIPCall(controller)

    # log.debug('SIP port queue: %d', Snapshot().sip.get_queue())

    Snapshot().sip.set_message_notification(ACU_SIP_REGISTER_NOTIFICATION)

    try:
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass

#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import logging
from aculab import defaultLogging, defaultOptions
from aculab.speech import SpeechChannel
from aculab.reactor import Reactor
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
        self.vmptx = VMPtx(controller, card=options.card,
                           module=options.module, user_data=self)
        self.vmprx = VMPrx(controller, card=options.card,
                           module=options.module, user_data=self)
        self.speech = SpeechChannel(controller, card=options.card,
                                    module=options.module, user_data=self)
        self.connection = None

    def connect(self):
        self.connection = connect((self.vmptx, self.vmprx), self.speech)

        #self.connection = Connection(
        #    endpoints = [self.vmptx.listen_to(self.speech.get_timeslot()),
        #                 self.speech.listen_to(self.vmprx.get_timeslot())])

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
        sd = vmprx.default_sdp()
        sd.intersect(user_data.in_sd)

        vmprx.configure(sd)

        log.debug('accepting call with SDP:\n%s', sd)

        user_data.call.accept(sd)

    def dtmf(self, channel, digit, user_data):
        # log.info('dtmf: %s', digit)
        pass

    def ev_incoming_call_det(self, call, user_data):
        sd = SDP(call.details.media_offer_answer.raw_sdp)

        call.user_data = CallData(self, call, sd)

        log.debug('got SDP:\n%s', sd)

        call.incoming_ringing()

    def ev_media(self, call, user_data):
        sd = SDP(call.details.media_session.received_media.raw_sdp)

        # Some CPEs seem to get confused when the TX doesn't have the same
        # port as the RX.
        user_data.vmptx.configure(sd, user_data.vmprx.get_rtp_address())

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_call_connected(self, call, user_data):
        user_data.connect()
        user_data.vmprx.config_tones(True, False)
        user_data.vmptx.config_tones(False, False)
        user_data.speech.listen_for('dtmf/fax')

        if not options.silent:
            user_data.speech.play(options.file_name)
        else:
            user_data.speech.record('sipin.al', max_silence = 5.0)

    def play_done(self, channel, reason, f, duration, user_data):
        # The call might be gone already
        if user_data.call:
            user_data.call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        if options.repeat:
            call.openin()
        else:    
            raise StopIteration
        

def usage():
    print '''usage: sipin.py [-n <numcalls>] [-r]'''
    sys.exit(-2)

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    parser = defaultOptions(
        description='Accept incoming SIP calls and play a prompt.',
        repeat=True)

    parser.add_option('-f', '--file-name', default='asteria.al',
                      help='Play FILE instead of asteria.al')

    parser.add_option('-n', '--numcalls', type='int', default=1,
                      help='Process NUMCALLS calls in parallel.')

    parser.add_option('-s', '--silent', action='store_true',
                      help="Don't play a prompt.")

    options, args = parser.parse_args()    
    
    controller = IncomingCallController()

    for i in range(options.numcalls):
        c = SIPCall(controller)

    # send automatic 200 OK for REGISTER - needed by the SpeedPort CPEs
    Snapshot().sip.set_message_notification(ACU_SIP_REGISTER_NOTIFICATION)

    try:
        Reactor.run()
    except StopIteration:
        pass

#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

# This example accepts an incoming SIP call and makes an outgoing ISDN call
# to the configured number


import sys
import logging
from urlparse import urlsplit
from urllib import splituser
from aculab import defaultLogging, defaultOptions
from aculab.speech import SpeechChannel
from aculab.reactor import Reactor
from aculab.callcontrol import CallHandle
from aculab.switching import Path, connect
from aculab.sip import SIPCall
from aculab.rtp import VMP
from aculab.sdp import SDP

class CallData:
    
    def __init__(self, controller, call):
        self.outcall = None
        self.incall = call
        self.dest = None
        self.in_sd = None
        self.out_sd = None
        self.path = Path(options.card, options.module)
        self.vmp = VMP(controller, card=options.card,
                       module=options.module, user_data=self)
        self.connection = []

    def connect(self):
        self.connection = [ connect(self.vmp, self.outcall) ]

    def connect_path(self):
        self.connection = [ self.outcall.listen_to(self.vmp.get_timeslot()),
                            self.path.listen_to(self.outcall),
                            self.vmp.listen_to(self.path) ]


    def ec(self):
        self.path.echocancel(self.vmp.rx, nonlinear = True)
        log.debug('path status: %d', self.path.get_status())

    def close(self):
        for attr in ['incall', 'outcall', 'vmp']:
            o = getattr(self, attr)
            if hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

        for c in self.connection:
            c.close()

class IncomingCallController:

    def ev_incoming_call_det(self, call, user_data):
        call.user_data = CallData(self, call)
        
        sd = SDP(call.details.media_offer_answer.raw_sdp)
        call.user_data.in_sd = sd

        to = urlsplit(call.details.destination_addr)[2]
        call.user_data.dest = splituser(to)[0]

        _from = urlsplit(call.details.originating_addr)[2]
        oad = splituser(_from)[0]

        log.debug('To "%s, From: %s" got SDP:\n%s', to, _from, sd)
        
        if oad and oad.isdigit():
            call.user_data.oad = oad
        else:
            call.user_data.oad = '0'
        
        call.incoming_ringing()

    def vmprx_ready(self, vmprx, user_data):
        """Called when the vmprx is ready."""
        user_data.out_sd = vmprx.default_sdp()
        user_data.out_sd.intersect(user_data.in_sd)

        vmprx.configure(user_data.out_sd)

        # make the outgoing call
        user_data.outcall = CallHandle(controller, card=options.card,
                                       port=options.port, user_data=user_data)

        user_data.outcall.openout(user_data.dest, True, user_data.oad)

    def ev_outgoing_ringing(self, call, user_data):
        log.debug('accepting call with SDP:\n%s', user_data.out_sd)
        user_data.incall.accept(user_data.out_sd)

    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()
        if call == user_data.outcall:
            user_data.incall.disconnect()
        else:
            user_data.outcall.disconnect()

    def ev_media(self, call, user_data):
        sd = SDP(call.details.media_session.received_media.raw_sdp)

        if options.ec:
            user_data.connect_path()
        else:
            user_data.connect()
            
        user_data.vmp.tx.configure(sd, user_data.vmp.rx.get_rtp_address())

    def ev_call_connected(self, call, user_data):
        if options.ec and call == user_data.outcall:
            user_data.ec()

    def ev_idle(self, call, user_data):
        incall = user_data.incall
        user_data.close()
        if options.repeat:
            incall.openin()
        else:
            raise StopIteration

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('app')

    parser = defaultOptions(repeat=True,
        description='Accept incoming SIP calls and forward them to PSTN. ' \
        'The username in the To: will be assumed to be the ' \
        'called party number.')

    parser.add_option('-e', '--ec', action='store_true', default = False,
                      help='perform echo cancellation on the ISDN leg')

    options, args = parser.parse_args()

    controller = IncomingCallController()

    c = SIPCall(controller)

    Reactor.run()


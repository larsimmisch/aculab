#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

import sys
import logging
from aculab import defaultLogging, defaultOptions
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor, CallReactor
from aculab.switching import connect
from aculab.sip import SIPCall, SIPHandle
from aculab.rtp import VMPrx, VMPtx, FMPrx, FMPtx
from aculab.sdp import SDP
from aculab.fax import T38GWSession
from aculab.snapshot import Snapshot
from aculab.lowlevel import ACU_SIP_REGISTER_NOTIFICATION


class Cleanup:
    '''Factored out the cleanup code.'''
    
    def close(self):
        for attr in ['connection', 'incall', 'outcall', 'speech', 'outvmprx',
                     'outvmptx', 'invmprx', 'invmptx', 'fmprx', 'fmptx']:
            o = getattr(self, attr, None)
            if o and hasattr(o, 'close'):
                o.close()
            setattr(self, attr, None)

class T30toT38(Cleanup):
    
    def __init__(self, controller, call, dest):
        # Create the call handle here, do the openout in ready

        self.in_sd = None
        self.incall = call
        self.invmptx = None
        self.invmprx = None
        if call.domain == 'sip':
            self.invmptx = VMPtx(controller, card=options.card,
                                 module=options.module, user_data=self)
            self.invmprx = VMPrx(controller, card=options.card,
                                 module=options.module, user_data=self)
            # for easier debugging
            self.invmprx.name = 'vrx-in'
            self.invmptx.name = 'vtx-in'
            
            self.in_sd = SDP(call.details.media_offer_answer.raw_sdp)

            log.debug('%s incoming call to: %s, from: %s with:\n%s', call.name,
                      call.details.destination_addr,
                      call.details.originating_addr, self.in_sd)
        else:
            log.debug('%s stream: %d timeslot: %d: features: %d',
                      call.name, call.details.stream, call.details.ts,
                      call.details.feature_information)

            
        self.outcall = SIPHandle(controller, self)
        self.outvmptx = VMPtx(controller, card=options.card,
                              module=options.module, user_data=self)
        self.outvmprx = VMPrx(controller, card=options.card,
                              module=options.module, user_data=self)
        # for easier debugging
        self.outvmprx.name = 'vrx-out'
        self.outvmptx.name = 'vtx-out'
        
        self.outfmptx = None
        self.outfmprx = None
        # self.speech = SpeechChannel(controller, card=options.card,
        #                             module=options.module, user_data=self)
        self.dest = dest
        self.connection = None

    def incall_ep(self):
        if self.incall.domain == 'pstn':
            return self.incall
        else:
            return (self.invmptx, self.invmprx)

    def outcall_ep(self):
        if self.outfmptx and self.outfmprx:
            return (self.outfmptx, self.outfmprx)

        return (self.outvmptx, self.outvmprx)

    def vmprx_ready(self, vmprx):
        if vmprx == self.invmprx:
            sd = vmprx.default_sdp()
            sd.intersect(self.in_sd)

            vmprx.configure(sd)    

            self.in_sd = sd
        else:
            self.out_sd = vmprx.default_sdp(True)

            log.debug('outgoing call to %s with:\n%s', self.dest,
                      self.out_sd)
        
            self.outcall.openout(self.dest, self.out_sd,
                                 custom_headers='X-Access: 0\r\nX-Flags: 2')
            vmprx.config_tones()

    def fmprx_ready(self, fmprx):
        sd = fmprx.default_sdp()

        self.outcall.media_accept(self.dest, sd)

    def ev_media(self, call):
        sd = SDP(call.details.media_session.received_media.raw_sdp)
        if call == self.incall:
        
            # Some CPEs seem to get confused when the TX doesn't have the same
            # port as the RX.
            self.invmptx.configure(sd, self.invmprx.get_rtp_address())
        else:
            sd.intersect(self.out_sd)
            self.outvmptx.configure(sd)

    def ev_media_propose(self, call):
        sd = SDP(call.details.media_offer_answer.raw_sdp)

        log.debug('got SDP: %s', sd)

        self.connection.close()
        self.fmptx = FMPtx(controller, card=options.card,
                           module=options.module, user_data=self)
        self.fmprx = FMPrx(controller, card=options.card,
                           module=options.module, user_data=self)

    def ev_call_connected(self, call):
        if call == self.outcall:
            if self.incall.domain == 'pstn':
                self.incall.accept()
            else:
                log.debug('accept incoming call with:\n%s', self.in_sd)
                self.incall.accept(self.in_sd)
        else:
            self.connection = connect(self.incall_ep(), self.outcall_ep())

    def ev_remote_disconnect(self, call):
        # Disconnect the other leg
        if call == self.incall:
            self.outcall.disconnect()
        elif call == self.outcall:
            self.incall.disconnect()

class T38toT30(Cleanup):
    pass
    
class T38GWController:

    def ev_incoming_call_det(self, call, user_data):
        if options.to_t38:
            call.user_data = T30toT38(self, call, dest)
        else:
            if call.domain == 'pstn':
                raise RuntimeIteration('cannot receive T.38 on a PSTN leg')
            call.user_data = T38toT30(self, call, dest)
                    
    def vmprx_ready(self, vmprx, user_data):
        user_data.vmprx_ready(vmprx)

    def fmprx_ready(self, fmprx, user_data):
        user_data.fvmprx_ready(fmprx)

    def dtmf(self, channel, digit, user_data):
        user_data.dtmf(channel, digit)

    def ev_media(self, call, user_data):
        user_data.ev_media(call)

    def ev_media_propose(self, call, user_data):
        user_data.ev_media_propose(call)

    def ev_remote_disconnect(self, call, user_data):
        user_data.ev_remote_disconnect(call)

    def ev_call_connected(self, call, user_data):
        user_data.ev_call_connected(call)
        
    def ev_idle(self, call, user_data):
        if user_data:
            user_data.close()
        
description = """Run a gateway between from T.38 to T.30. NUMBER is the
destination number or URI (without the scheme part). A number with a '.' or an '@' is interpreted as a SIP destination. By default, it is attempted to receive a FAX on the T.38 leg and send it to the T.30 leg."""

if __name__ == '__main__':

    defaultLogging(logging.DEBUG)
    log = logging.getLogger('t38gw')

    parser = defaultOptions(
        usage='usage: %prog [options] NUMBER',
        description=description, repeat=True)

    parser.add_option('-n', '--numcalls', type='int', default=1,
                      help='Process NUMCALLS calls in parallel.')

    parser.add_option('-s', '--to-t38', action='store_true',
                      help='send the FAX to a T.38 endpoint.')

    options, args = parser.parse_args()    

    if not args:
        parser.print_help()
        sys.exit(2)

    dest = args[0]

    # send automatic 200 OK for REGISTER - needed by the SpeedPort CPEs
    Snapshot().sip.set_message_notification(ACU_SIP_REGISTER_NOTIFICATION)

    controller = T38GWController()

    for i in range(options.numcalls):
        Call(controller, card=options.card, port=options.port)
        SIPCall(controller) 

    # We need a T38GWSession. It should be good for about 6 concurrent calls.
    T38Session = T38GWSession()
    T38Session.start()
    # Start the usual reactors
    SpeechReactor.start()
    CallReactor.run()

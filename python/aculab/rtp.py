"""RTP and speech processing functions.

This module contains speech RTP transmitters and receivers (L{VMPtx} and
L{VMPrx})."""

import sys
import os
import time
import logging
import lowlevel
import names
import sdp
from switching import VMPtxEndpoint, TDMrx
from reactor import SpeechReactor
from snapshot import Snapshot
from error import *
from util import Lockable, os_event, translate_card

import select

log = logging.getLogger('rtp')
log_switch = logging.getLogger('switch')

rfc2833_digits = {
    0: '0', 1: '1', 2: '2', 3: '3', 4: '4',
    5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
    10: '*', 11: '#', 12: 'A', 13: 'B', 14: 'C', 15: 'D',
    16: 'R', 32: 'ANS', 33: '/ANS', 34: 'ANSam', 35: '/ANSam', 36: 'CNG',
    37: 'V21_1_0', 38: 'V21_1_1', 39: 'V21_2_0', 40: 'V21_2_1',
    41: 'CRdi', 42: 'CRdr', 43: 'CRe', 44: 'ESi', 45: 'ESr', 46: 'MRdi',
    47: 'MRdr', 48: 'MRe', 49: 'CT' }

class RTPBase(Lockable):
    """Internal baseclass for RTP tx/rx classes that manages connections
    to the TDM bus"""
    
    def __init__(self, card, module, mutex, user_data, ts_type):
        Lockable.__init__(self, mutex)
        self.card, self.module = translate_card(card, module)
        self.user_data = user_data
        self.ts_type = ts_type
        self.tdm = None

    def close(self):
        """Close the TDM connection."""
        if self.tdm:
            self.tdm.close()
            self.tdm = None

    def get_module(self):
        """Return a unique identifier for module comparisons.
        Used by switching."""

        return self.module

    def get_switch(self):
        """Return a unique identifier for switch card comparisons.
        Used by switching."""

        return self.card

    def get_timeslot(self):
        """Return the tx timeslot for TDM switch connections."""
        if not self.tdm:
            self.tdm_connect()

        return self.tdm.timeslots[0]

    def get_module(self):
        """Return a unique identifier for module comparisons.
        Used by switching."""

        return self.module

    def get_switch(self):
        """Return a unique identifier for switch card comparisons.
        Used by switching."""

        return self.card

class VMPrx(RTPBase):
    """An RTP receiver."""

    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):
        """Allocate an RTP receiver, configure alaw/mulaw and RFC 2833 codecs
        and add the event to the reactor.

        Note: the VMPrx is not ready to use until it has called 'ready' on its
        controller.
        
        Controllers must implement:
         - ready(vmprx, sdp, user_data)
         - dtmf(vmprx, digit, user_data)."""

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)
        
        self.controller = controller
        self.reactor = reactor

        # initialize early
        self.vmprx = None
        self.event_vmprx = None
        self.datafeed = None
        self.rtp_port = None
        self.rtcp_port = None
        self.sdp = None
        self.tdm = None

        # create vmprx
        vmprx = lowlevel.SM_VMPRX_CREATE_PARMS()
        vmprx.module = self.module.open.module_id
        # vmprx.set_address(self.card.ip_address)
        rc = lowlevel.sm_vmprx_create(vmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_create')

        self.vmprx = vmprx.vmprx

        self.name = 'vrx-%08x' % self.vmprx

        # get the event
        evmprx = lowlevel.SM_VMPRX_EVENT_PARMS()
        evmprx.vmprx = self.vmprx

        rc = lowlevel.sm_vmprx_get_event(evmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_event')

        self.event_vmprx = os_event(evmprx.event)

        log.debug('%s event fd: %d', self.name, self.event_vmprx)

        # get the datafeed
        datafeed = lowlevel.SM_VMPRX_DATAFEED_PARMS()

        datafeed.vmprx = self.vmprx
        rc = lowlevel.sm_vmprx_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_datafeed')

        self.datafeed = datafeed.datafeed

        self.reactor.add(self.event_vmprx, self.on_vmprx, select.POLLIN)
        
    def close(self):
        """Stop the receiver."""

        RTPBase.close(self)

        if self.vmprx:
            stopp = lowlevel.SM_VMPRX_STOP_PARMS()
            stopp.vmprx = self.vmprx

            rc = lowlevel.sm_vmprx_stop(stopp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_stop')

            log.debug("%s stopping", self.name)

    def on_vmprx(self):
        """Internal event handler."""
        
        status = lowlevel.SM_VMPRX_STATUS_PARMS()
        status.vmprx = self.vmprx

        rc = lowlevel.sm_vmprx_status(status)
        log.debug('%s vmprx status: %s', self.name,
                  names.vmprx_status_names[status.status])
        
        if status.status == lowlevel.kSMVMPrxStatusGotPorts:
            self.rtp_port = status.u.ports.RTP_Port
            self.rtcp_port = status.u.ports.RTCP_Port
            self.address = status.get_ports_address()
            # self.rtp_address = status.ports_address()
            log.debug('%s vmprx: rtp address: %s rtp port: %d, rtcp port: %d',
                      self.name, self.address, self.rtp_port, self.rtcp_port)

            self.default_codecs()
        
            # Create the SDP
            md = sdp.MediaDescription()
            md.setLocalPort(self.rtp_port)
            md.addRtpMap(sdp.PT_PCMU)
            md.addRtpMap(sdp.PT_PCMA)
            md.addRtpMap(sdp.PT_NTE)
    
            self.sdp = sdp.SDP()
            self.sdp.setServerIP(self.address)
            self.sdp.addMediaDescription(md)

            self.controller.ready(self, self.sdp, self.user_data)

        elif status.status == lowlevel.kSMVMPrxStatusDetectTone:
            tone = status.u.tone.id
            volume = status.u.tone.volume
            log.debug('%s vmprx: tone: %d, volume: %f', self.name,
                      tone, volume)

            self.controller.dtmf(self, rfc2833_digits[tone], self.user_data)
            
        elif status.status == lowlevel.kSMVMPrxStatusStopped:
            self.reactor.remove(self.event_vmprx)
            self.event_vmprx = None
            self.datafeed = None
            
            rc = lowlevel.sm_vmprx_destroy(self.vmprx)
            self.vmprx = None

            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_destroy')

    def tdm_connect(self):
        """Connect the Receiver to a timeslot on its DSP's timeslot range.
        This method internally allocates a L{TDMtx} on the module's
        timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""
        self.tdm = Connection(self.module.timeslots)

        ts = self.module.timeslots.allocate(self.ts_type)

        tx = TDMtx(ts, self.card, self.module)
        tx.listen_to(self)

        self.tdm.add(tx, ts)

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed
            
    def config_tones(self, detect = True, regen = False):
        """Configure RFC2833 tone detection/regeneration."""
        
        tones = lowlevel.SM_VMPRX_TONE_PARMS()
        tones.vmprx = self.vmprx
        tones.regen_tones = regen
        tones.detect_tones = detect

        rc = lowlevel.sm_vmprx_config_tones(tones)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_config_tones')

    def config_codec(self, codec, pt, plc_mode = lowlevel.kSMPLCModeDisabled):
        """Configure a (generic) codec."""
        
        codecp = lowlevel.SM_VMPRX_CODEC_PARMS()
        codecp.vmprx = self.vmprx
        codecp.codec = codec
        codecp.payload_type = pt
        codecp.plc_mode = plc_mode
    
        rc = lowlevel.sm_vmprx_config_codec(codecp)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_config_codec')

    def config_rfc2833(self, pt = 101, plc_mode = lowlevel.kSMPLCModeDisabled):
        """Configure the RFC2833 codec."""
        
        rfc2833 = lowlevel.SM_VMPRX_CODEC_RFC2833_PARMS()
        rfc2833.vmprx = self.vmprx
        rfc2833.payload_type = pt
        rfc2833.plc_mode = plc_mode

        rc = lowlevel.sm_vmprx_config_codec_rfc2833(rfc2833)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_config_codec_rfc2833')

    def default_codecs(self):
        """Preliminary: just alaw/mulaw/rfc2833. No connection to SDP yet."""

        self.config_codec(lowlevel.kSMCodecTypeAlaw, 0)
        self.config_codec(lowlevel.kSMCodecTypeMulaw, 8)
        self.config_rfc2833()

class VMPtx(RTPBase):
    """An RTP transmitter."""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)

        self.controller = controller
        self.reactor = reactor

        # initialize early 
        self.event_vmptx = None
        self.event_vmprx = None

        # create vmptx
        vmptx = lowlevel.SM_VMPTX_CREATE_PARMS()
        vmptx.module = self.module.open.module_id
        rc = lowlevel.sm_vmptx_create(vmptx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_create')

        self.vmptx = vmptx.vmptx
        self.name = 'vtx-%08x' % self.vmptx

        evmptx = lowlevel.SM_VMPTX_EVENT_PARMS()
        evmptx.vmptx = self.vmptx

        rc = lowlevel.sm_vmptx_get_event(evmptx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_get_event')

        self.event_vmptx = os_event(evmptx.event)

        log.debug('%s event fd: %d', self.name, self.event_vmptx)

        self.reactor.add(self.event_vmptx, self.on_vmptx, select.POLLIN)

    def close(self):
        """Stop the transmitter."""

        RTPBase.close(self)

        if self.vmptx:
            stopp = lowlevel.SM_VMPTX_STOP_PARMS()
            stopp.vmptx = self.vmptx

            rc = lowlevel.sm_vmptx_stop(stopp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_stop')

            log.debug("%s stopping", self.name)

    def __del__(self):
        self.close()

    def on_vmptx(self):
        status = lowlevel.SM_VMPTX_STATUS_PARMS()
        status.vmptx = self.vmptx

        rc = lowlevel.sm_vmptx_status(status)
        log.debug('%s vmptx status: %s', self.name,
                  names.vmptx_status_names[status.status])

        if status.status == lowlevel.kSMVMPtxStatusStopped:
            self.reactor.remove(self.event_vmptx)
            self.event_vmptx = None
            
            rc = lowlevel.sm_vmptx_destroy(self.vmptx)
            self.vmptx = None

    def tdm_connect(self):
        """Connect the Tranmitter to a timeslot on its DSP's timeslot range.
        This method internally allocates a L{TDMtx} on the module's
        timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""
        self.tdm = Connection(self.module.timeslots)

        ts = self.module.timeslots.allocate(self.ts_type)

        rx = TDMrx(ts, self.card, self.module)
        self.listen_to(rx)

        self.tdm.add(rx, ts)

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def configure(self, sdp):
        """Configure the Transmitter according to the SDP.

        @param sdp: An instance of class L{SDP}."""

        config = lowlevel.SM_VMPTX_CONFIG_PARMS()
        config.vmptx = self.vmptx
        addr = sdp.getAddress('audio')

        log.debug('%s destination: %s', self.name, addr)
        
        config.set_destination_rtp(addr)

        rc = lowlevel.sm_vmptx_config(config)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config')

        md = sdp.getMediaDescription('audio')
        for k, v in md.rtpmap.iteritems():
            m = v[1]
            if m.name == 'PCMU':
                self.config_codec(lowlevel.kSMCodecTypeMulaw, k)
            elif m.name == 'PCMA':
                self.config_codec(lowlevel.kSMCodecTypeAlaw, k)
            elif m.name == 'G729':
                self.config_codec(lowlevel.kSMCodecTypeG729AB, k)
            elif m.name == 'telephone-event':
                self.config_rfc2833(k)
            else:
                log.warn('Codec %d %s unsupported', k, m.name)
            
    def config_tones(self, convert = 0, elim = 1):
        """Configure RFC2833 tone conversion/elimination.
        By default, don't convert tones, but eliminate them."""
        
        tones = lowlevel.SM_VMPTX_TONE_PARMS()
        tones.vmptx = self.vmptx
        tones.convert_tones = convert
        tones.elim_tones = elim

        rc = lowlevel.sm_vmptx_config_tones(tones)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_tones')

    def config_codec(self, codec, pt,
                     vad_mode = lowlevel.kSMVMPTxVADModeDisabled,
                     ptime = 20):
        """Configure a (generic) codec.

        By default, do not do voice activity detection (i.e. always send data)
        and send 20ms of data in each packets

        @param vad_mode: voice activity detection mode.
        @param ptime: how much data (in ms) to send per packet per packet.
        """
        
        codecp = lowlevel.SM_VMPTX_CODEC_PARMS()
        codecp.vmptx = self.vmptx
        codecp.codec = codec
        codecp.payload_type = pt
        codecp.ptime = ptime
    
        rc = lowlevel.sm_vmptx_config_codec(codecp)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_codec')

    def config_rfc2833(self, pt = 101):
        """Configure the RFC2833 codec."""
        
        rfc2833 = lowlevel.SM_VMPTX_CODEC_RFC2833_PARMS()
        rfc2833.vmptx = self.vmptx
        rfc2833.payload_type = pt

        rc = lowlevel.sm_vmptx_config_codec_rfc2833(rfc2833)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_codec_rfc2833')

    def listen_to(self, other):
        if hasattr(other, 'get_datafeed'):
            connect = lowlevel.SM_VMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.vmptx
            connect.data_source = other.get_datafeed()

            rc = lowlevel.sm_vmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_datafeed_connect')

            log_switch.debug('%s := %s', self.name, other.name)

            return VMPtxEndpoint(self)
        else:
            tdm = TDMrx(other, self.card, self.module)
            
            connect = lowlevel.SM_VMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.vmptx
            connect.data_source = tdm.get_datafeed()

            rc = lowlevel.sm_vmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_datafeed_connect')

            log_switch.debug('%s := %s', self.name, other.name)

            return VMPtxEndpoint(self, tdm)

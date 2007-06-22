"""RTP and speech processing functions.

This module contains RTPChannel. RTPChannel is a subclass of SpeechChannel,
with additional RTP capabilities."""

import sys
import os
import time
import logging
import lowlevel
import names
import sdp
from snapshot import Snapshot
from error import *
from util import Lockable
from speech import SpeechDispatcher, os_event, translate_card
import select

log = logging.getLogger('rtp')

rfc2833_digits = {
    0: '0', 1: '1', 2: '2', 3: '3', 4: '4',
    5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
    10: '*', 11: '#', 12: 'A', 13: 'B', 14: 'C', 15: 'D',
    16: 'R', 32: 'ANS', 33: '/ANS', 34: 'ANSam', 35: '/ANSam', 36: 'CNG',
    37: 'V21_1_0', 38: 'V21_1_1', 39: 'V21_2_0', 40: 'V21_2_1',
    41: 'CRdi', 42: 'CRdr', 43: 'CRe', 44: 'ESi', 45: 'ESr', 46: 'MRdi',
    47: 'MRdr', 48: 'MRe', 49: 'CT' }

class VMPrx(Lockable):
    """An RTP receiver."""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, dispatcher = SpeechDispatcher):
        """Allocate an RTP receiver, configure alaw/mulaw and RFC 2833 codecs
        and add the event to the dispatcher.

        Note: the VMPrx is not ready to use until it has called 'ready' on its
        controller.
        
        Controllers must implement:
        - ready(vmprx, sdp, user_data)
        - dtmf(vmprx, digit, user_data)."""

        Lockable.__init__(self, mutex)

        self.controller = controller
        self.card, self.module = translate_card(card, module)
        self.dispatcher = dispatcher
        self.user_data = user_data

        # initialize early 
        self.vmprx = None
        self.event_vmprx = None
        self.rtp_port = None
        self.rtcp_port = None
        self.sdp = None

        # create vmprx
        vmprx = lowlevel.SM_VMPRX_CREATE_PARMS()
        vmprx.module = self.module.open.module_id
        # vmprx.set_address(self.card.ip_address)
        rc = lowlevel.sm_vmprx_create(vmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_create')

        self.vmprx = vmprx.vmprx

        self.name = '0x%04x' % self.vmprx

        # get the event
        evmprx = lowlevel.SM_VMPRX_EVENT_PARMS()
        evmprx.vmprx = self.vmprx

        rc = lowlevel.sm_vmprx_get_event(evmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_event')

        self.event_vmprx = os_event(evmprx.event)

        # log.debug('%s event fd: %d', self.name, self.event_vmprx.fd)

        # get the datafeed
        datafeed = lowlevel.SM_VMPRX_DATAFEED_PARMS()

        datafeed.vmprx = self.vmprx
        rc = lowlevel.sm_vmprx_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_datafeed')

        self.datafeed = datafeed.datafeed

        self.default_codecs()

        self.dispatcher.add(self.event_vmprx, self.on_vmprx, select.POLLIN)
        
    def _close(self):
        self.lock()
        try:
            if self.vmprx:
                lowlevel.smd_vmprx_destroy(self.vmprx)
                self.vmprx = None
                self.event_vmprx = None
        finally:
            self.unlock()        

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

            self.controller.dtmf(self, rfc2933_digits[tone], self.user_data)
            
    def config_tones(self, detect = 1, regen = 0):
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

class VMPtx:
    """An RTP transmitter."""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, dispatcher = SpeechDispatcher):

        Lockable.__init__(self, mutex)

        self.controller = controller
        self.card, self.module = translate_card(card, module)
        self.dispatcher = dispatcher
        self.user_data = user_data

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
        self.name = '0x%04x' % self.vmptx

        evmptx = lowlevel.SM_VMPTX_EVENT_PARMS()
        evmptx.vmptx = self.vmptx

        rc = lowlevel.sm_vmptx_get_event(evmptx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_get_event')

        self.event_vmptx = os_event(evmptx.event)

        log.debug('vmptx event: %d', self.event_vmptx.fd)
        
        self.dispatcher.add(self.event_vmptx, self.on_vmptx, select.POLLIN)

    def _close(self):
        self.lock()
        try:
            if self.vmptx:
                lowlevel.smd_vmptx_destroy(self.vmptx)
                self.vmptx = None
                self.event_vmptx = None
        finally:
            self.unlock()
        
    def __del__(self):
        self._close()

    def on_vmptx(self):
        status = lowlevel.SM_VMPTX_STATUS_PARMS()
        status.vmptx = self.vmptx

        rc = lowlevel.sm_vmptx_status(status)
        log.debug('%s vmptx status: %s', self.name,
                  names.vmptx_status_names[status.status])
            
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
    
        rc = lowlevel.sm_vmptx_config_codec(codecp)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_codec')

    def config_rfc2833(self, pt = 101):
        """Configure the RFC2833 codec."""
        
        rfc2833 = lowlevel.SM_VMPRX_CODEC_RFC2833_PARMS()
        rfc2833.vmprx = self.vmprx
        rfc2833.payload_type = pt

        rc = lowlevel.sm_vmptx_config_codec_rfc2833(rfc2833)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_codec_rfc2833')
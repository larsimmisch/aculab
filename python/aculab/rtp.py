# Copyright (C) 2007-2008 Lars Immisch

"""RTP and speech processing functions.

This module contains RTP transmitters and receivers for speech (L{VMPtx} and
L{VMPrx}) and T.38 (L{FMPtx} and L{FMPrx})."""

import sys
import os
import time
import logging
import lowlevel
import names
import sdp
import socket
from switching import VMPtxEndpoint, FMPtxEndpoint, TDMrx, TDMtx, Connection
from reactor import SpeechReactor, add_event
from snapshot import Snapshot
from error import *
from util import Lockable, translate_card

import select

log = logging.getLogger('rtp')
log_switch = logging.getLogger('switch')

rfc2833_id2name = {
    0: '0', 1: '1', 2: '2', 3: '3', 4: '4',
    5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
    10: '*', 11: '#', 12: 'A', 13: 'B', 14: 'C', 15: 'D',
    16: 'R', 32: 'ANS', 33: '/ANS', 34: 'ANSam', 35: '/ANSam', 36: 'CNG',
    37: 'V21_1_0', 38: 'V21_1_1', 39: 'V21_2_0', 40: 'V21_2_1',
    41: 'CRdi', 42: 'CRdr', 43: 'CRe', 44: 'ESi', 45: 'ESr', 46: 'MRdi',
    47: 'MRdr', 48: 'MRe', 49: 'CT' }

rfc2833_name2id = {
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
    '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '*': 10, '#': 11, 'A': 12, 'B': 13, 'C': 14, 'D': 15,
    'R': 16, 'ANS': 32, '/ANS': 33, 'ANSam': 34, '/ANSam': 35, 'CNG': 36,
    'V21_1_0': 37, 'V21_1_1': 38, 'V21_2_0': 39, 'V21_2_1': 40,
    'CRdi': 41, 'CRdr': 42, 'CRe': 43, 'ESi': 44, 'ESr': 45, 'MRdi': 46,
    'MRdr': 47, 'MRe': 48, 'CT': 49 }

class RTPBase(Lockable):
    """Internal baseclass for RTP tx/rx classes that manages connections
    to the TDM bus"""
    
    def __init__(self, card, module, mutex, user_data, ts_type):
        Lockable.__init__(self, mutex)
        self.user_data = user_data
        self.ts_type = ts_type
        self.tdm = None
        self.card, self.module = translate_card(card, module)

    def close(self):
        """Close the TDM connection."""
        self.user_data = None
            
        if self.tdm:
            self.tdm.close()
            self.tdm = None

    def rx_tdm_connect(self):
        """For Receiver subclasses: connect to a timeslot on its
        DSP's timeslot range.
        This method internally allocates a L{TDMtx} on the module's
        timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""
        self.tdm = Connection(self.module.timeslots)

        ts = self.module.timeslots.allocate(self.ts_type)

        tx = TDMtx(ts, self.card, self.module)
        tx.listen_to(self)

        self.tdm.add(tx, ts)

    def tx_tdm_connect(self):
        """For Transmitter subclasses: connect to a timeslot on its DSP's
        timeslot range.
        
        This method internally allocates a L{TDMrx} on the module's
        timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""
        self.tdm = Connection(self.module.timeslots)

        ts = self.module.timeslots.allocate(self.ts_type)

        rx = TDMrx(ts, self.card, self.module)
        self.listen_to(rx)

        self.tdm.add(rx, ts)


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
            self.rx_tdm_connect()

        return self.tdm.timeslots[0]

class VMPrx(RTPBase):
    """An RTP speech receiver.

    Logging: output from a VMPrx is prefixed with C{vrx-}"""

    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):
        """Allocate an RTP receiver, configure alaw/mulaw and RFC 2833 codecs
        and add the event to the reactor.

        Note: the VMPrx is not ready to use until it has called 'vmprx_ready'
        on its controller.
        
        Controllers must implement:
         - vmprx_ready(vmprx, user_data)
         - vmprx_newssrc(vmprx, address, ssrc, user_data)
         - dtmf(vmprx, digit, user_data)."""

        self.controller = controller
        self.reactor = reactor

        # initialize early
        self.vmprx = None
        self.event_vmprx = None
        self.datafeed = None
        self.rtp_port = None
        self.rtcp_port = None
        self.address = socket.INADDR_ANY

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)
        
        # create vmprx
        vmprx = lowlevel.SM_VMPRX_CREATE_PARMS()
        vmprx.module = self.module.open.module_id
        # vmprx.set_address(self.card.ip_address)
        rc = lowlevel.sm_vmprx_create(vmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_create')

        self.vmprx = vmprx.vmprx

        self.name = 'vrx-%08x' % self.vmprx

        # get the datafeed
        datafeed = lowlevel.SM_VMPRX_DATAFEED_PARMS()

        datafeed.vmprx = self.vmprx
        rc = lowlevel.sm_vmprx_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_datafeed')

        self.datafeed = datafeed.datafeed

        # get the event
        evmprx = lowlevel.SM_VMPRX_EVENT_PARMS()
        evmprx.vmprx = self.vmprx

        # log.debug('%s event fd: %d', self.name, self.event_vmprx)

        rc = lowlevel.sm_vmprx_get_event(evmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_get_event')

        self.event_vmprx = add_event(self.reactor, evmprx.event, self.on_vmprx)
        
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

    def get_rtp_address(self):
        "Return the RTP address and port as a Python-friendly tuple."

        return (self.address, self.rtp_port)

    def get_rtcp_address(self):
        "Return the RTCP address and port as a Python-friendly tuple."

        return (self.address, self.rtcp_port)

    def on_vmprx(self):
        """Internal event handler."""
        
        status = lowlevel.SM_VMPRX_STATUS_PARMS()
        status.vmprx = self.vmprx

        rc = lowlevel.sm_vmprx_status(status)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_status')
        
        if status.status == lowlevel.kSMVMPrxStatusGotPorts:
            self.rtp_port = status.u.ports.RTP_Port
            self.rtcp_port = status.u.ports.RTCP_Port
            self.address = status.get_address()
            # self.rtp_address = status.ports_address()
            log.debug('%s rtp address: %s rtp port: %d, rtcp port: %d',
                      self.name, self.address, self.rtp_port, self.rtcp_port)

            self.controller.vmprx_ready(self, self.user_data)

        elif status.status == lowlevel.kSMVMPrxStatusDetectTone:
            tone = status.u.tone.id
            volume = status.u.tone.volume
            log.debug('%s tone: %d, volume: %f', self.name,
                      tone, volume)

            self.controller.dtmf(self, rfc2833_id2name[tone], self.user_data)
            
        elif status.status == lowlevel.kSMVMPrxStatusEndTone:
            # ignore in the logging
            pass
        
        elif status.status == lowlevel.kSMVMPrxStatusNewSSRC:
            log.debug('%s new SSRC: %s, port: %d, ssrc: %d', self.name,
                      status.get_address(), status.u.ssrc.port,
                      status.u.ssrc.ssrc)

            if hasattr(self.controller, 'vmprx_newssrc'):
                self.controller.vmprx_newssrc(
                    self, (status.get_address, status.u.ssrc.port),
                    status.u.ssrc.ssrc, self.user_data)

        elif status.status == lowlevel.kSMVMPrxStatusStopped:
            # log.debug('%s vmprx stopped (%d)', self.name, self.event_vmprx)
            self.reactor.remove(self.event_vmprx)
            self.event_vmprx = None
            self.datafeed = None
            
            rc = lowlevel.sm_vmprx_destroy(self.vmprx)
            self.vmprx = None

            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_destroy')
        else:
            log.debug('%s vmprx status: %s', self.name,
                      names.vmprx_status_names[status.status])
            
    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def media_description(self, enable_rfc2833 = True):
        """Return a media description with all supported codecs."""
        
        md = sdp.MediaDescription()
        md.setLocalPort(self.rtp_port)
        md.addRtpMap(sdp.PT_PCMA)
        md.addRtpMap(sdp.PT_PCMU)
        if enable_rfc2833:
            md.addRtpMap(sdp.PT_NTE)

        return md
        
    def default_sdp(self, configure=False, enable_rfc2833 = True):
        # Create a default SDP

        sd = sdp.SDP()
        
        sd.addMediaDescription(self.media_description(enable_rfc2833))

        sd.setServerIP(self.address)

        if configure:
            self.configure(sd)

        return sd

    def config_codec(self, pt, fmt, plc_mode = lowlevel.kSMPLCModeDisabled):
        """Configure a codec.

        @param pt: The payload type as an int.
        @param fmt: a L{PTMarker} decribing the codec.
        """
        if fmt.name == 'PCMU':
            codecp = lowlevel.SM_VMPRX_CODEC_MULAW_PARMS()
            codecp.vmprx = self.vmprx
            codecp.payload_type = pt
            codecp.plc_mode = plc_mode
    
            rc = lowlevel.sm_vmprx_config_codec_mulaw(codecp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_config_codec_mulaw')
                
        elif fmt.name == 'PCMA':
            codecp = lowlevel.SM_VMPRX_CODEC_ALAW_PARMS()
            codecp.vmprx = self.vmprx
            codecp.payload_type = pt
            codecp.plc_mode = plc_mode
    
            rc = lowlevel.sm_vmprx_config_codec_alaw(codecp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_config_codec_alaw')

        elif fmt.name == 'telephone-event':
            rfc2833 = lowlevel.SM_VMPRX_CODEC_RFC2833_PARMS()
            rfc2833.vmprx = self.vmprx
            rfc2833.payload_type = pt
            rfc2833.plc_mode = plc_mode
            
            rc = lowlevel.sm_vmprx_config_codec_rfc2833(rfc2833)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmprx_config_codec_rfc2833')
        else:
            raise RuntimeError('unsupported codec %s' % self.name)

        log.debug('%s codec: %s pt: %d', self.name, fmt.name, pt)        
        
    def configure(self, sd, plc_mode = lowlevel.kSMPLCModeDisabled):
        """Configure the Receiver according to the SDP.

        @param sd: A L{SDP} instance describing the session."""

        md = sd.getMediaDescription('audio')

        if not md or not md.formats:
            log.warn('%s no audio description or empty format list', self.name)
            return

        # Configure the first codec
        pt = int(md.formats[0])
        self.config_codec(pt, md.rtpmap[pt][1], plc_mode)
        
        # Now check for RFC2833
        for k, v in md.rtpmap.iteritems():
            m = v[1]
            if m.name == 'telephone-event':
                self.config_codec(k, m, plc_mode)

                
    def config_tones(self, detect = True, regen = False):
        """Configure RFC2833 tone detection/regeneration."""
        
        tones = lowlevel.SM_VMPRX_TONE_PARMS()
        tones.vmprx = self.vmprx
        tones.regen_tones = regen
        tones.detect_tones = detect

        rc = lowlevel.sm_vmprx_config_tones(tones)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmprx_config_tones')

class VMPtx(RTPBase):
    """An RTP speech data transmitter.

    Logging: output from a VMPtx is prefixed with C{vtx-}"""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):

        self.controller = controller
        self.reactor = reactor

        # initialize early 
        self.vmptx = None
        self.event_vmptx = None

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)

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

        self.event_vmptx = add_event(self.reactor, evmptx.event, self.on_vmptx)

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
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_status')

        if status.status == lowlevel.kSMVMPtxStatusStopped:
            log.debug('%s vmptx stopped', self.name)

            self.reactor.remove(self.event_vmptx)
            self.event_vmptx = None
            
            rc = lowlevel.sm_vmptx_destroy(self.vmptx)
            self.vmptx = None
        else:
            log.debug('%s vmptx status: %s', self.name,
                      names.vmptx_status_names[status.status])

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def listen_to(self, source):
        """Listen to a timeslot or a tx instance.

        I{Switching protocol}. Applications should
        generally use L{switching.connect}.
        
        @param source: a tuple (stream, timeslot, [timeslot_type]) or a
        transmitter instance (L{VMPtx}, L{FMPtx} or L{TDMtx}), which must be on
        the same module."""
        
        if hasattr(source, 'get_datafeed') and source.get_datafeed():
            connect = lowlevel.SM_VMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.vmptx
            connect.data_source = source.get_datafeed()

            rc = lowlevel.sm_vmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_datafeed_connect')

            log_switch.debug('%s := %s (datafeed)', self.name, source.name)

            return VMPtxEndpoint(self)
        else:
            if not self.tdm:
                self.tx_tdm_connect()
            
            self.tdm.endpoints[0].listen_to(source)
            
            # log_switch.debug('%s := %d:%d', self.name, source[0], source[1])

            return VMPtxEndpoint(self)

    def config_codec(self, pt, fmt,
                     vad_mode = lowlevel.kSMVMPTxVADModeDisabled,
                     ptime = 20):
        """Configure a codec.

        @param pt: The payload type as an int.
        @param fmt: a L{PTMarker} decribing the codec.
        """
        if fmt.name == 'PCMU':
            codecp = lowlevel.SM_VMPTX_CODEC_MULAW_PARMS()
            codecp.vmptx = self.vmptx
            codecp.payload_type = pt
            codecp.ptime = ptime
            codecp.VADMode = vad_mode
            
            rc = lowlevel.sm_vmptx_config_codec_mulaw(codecp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_config_codec_mulaw')
                    
        elif fmt.name == 'PCMA':
            codecp = lowlevel.SM_VMPTX_CODEC_ALAW_PARMS()
            codecp.vmptx = self.vmptx
            codecp.payload_type = pt
            codecp.ptime = ptime
            codecp.VADMode = vad_mode
            
            rc = lowlevel.sm_vmptx_config_codec_alaw(codecp)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_config_codec_alaw')
            
        elif fmt.name == 'telephone-event':
            rfc2833 = lowlevel.SM_VMPTX_CODEC_RFC2833_PARMS()
            rfc2833.vmptx = self.vmptx
            rfc2833.payload_type = pt

            rc = lowlevel.sm_vmptx_config_codec_rfc2833(rfc2833)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_config_codec_rfc2833')

        else:
            raise RuntimeError('unsupported codec %s' % fmt.name)

        log.debug('%s codec: %s pt: %d', self.name, fmt.name, pt)

    def configure(self, sdp, source_rtp = None, source_rtcp = None,
                  vad_mode = lowlevel.kSMVMPTxVADModeDisabled,
                  ptime = 20):
        """Configure the Transmitter according to the SDP.

        By default, do not do voice activity detection (i.e. don't do silence
        suppression) and send 20ms of data in each packet.

        @param sdp: An instance of class L{SDP}.

        @param source_rtp: the receivers source rtp address (as a tuple)
        Needed for symmetric RTP.
        @param source_rtcp: the receivers source rtcp address (as a tuple)
        @param vad_mode: voice activity detection mode.
        @param ptime: how much data (in ms) to send per packet per packet.
        """

        config = lowlevel.SM_VMPTX_CONFIG_PARMS()
        config.vmptx = self.vmptx
        addr = sdp.getAddress('audio')

        log.debug('%s destination: %s', self.name, addr)
        
        config.set_destination_rtp(addr)

        if source_rtp:
            config.set_source_rtp(source_rtp)

        if source_rtcp:
            config.set_source_rtp(rtcp)

        rc = lowlevel.sm_vmptx_config(config)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config')

        md = sdp.getMediaDescription('audio')
        
        if not md or not md.formats:
            log.warn('%s no audio description or empty format list', self.name)
            return

        # Configure the first codec
        pt = int(md.formats[0])
        self.config_codec(pt, md.rtpmap[pt][1], vad_mode, ptime)
        
        # Now check for RFC2833
        for k, v in md.rtpmap.iteritems():
            m = v[1]
            if m.name == 'telephone-event':
                self.config_codec(k, m, vad_mode, ptime)

    def config_tones(self, convert = False, elim = True):
        """Configure RFC2833 tone conversion/elimination.
        By default, don't convert tones, but eliminate them."""
        
        tones = lowlevel.SM_VMPTX_TONE_PARMS()
        tones.vmptx = self.vmptx
        tones.convert_tones = convert
        tones.elim_tones = elim
        tones.tone_set_id = self.module.vmptx_default_toneset()

        rc = lowlevel.sm_vmptx_config_tones(tones)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_config_tones')

    def tones(self, tones, length = 0.04, interval = 0.1):
        """Send RFC 2833 digits.

        @param tones: a list of RFC 2833 tone names. I{See} L{rfc2833_id2name}
        for a list of valid names.
        @param length: the length in seconds. Must be a multiple of 0.01
        (10ms). The default is 0.04s (40ms).
        @param interval: the interval between tones, in seconds. The default
        is 0.1s (100ms)."""

        tp = lowlevel.SM_VMPTX_GENERATE_TONE_PARMS()
        tp.vmptx = self.vmptx
        tp.duration = int(duration * 1000)
        tp.interval = int(interval * 1000)
        
        rc = lowlevel.sm_vmptx_generate_tones(tp)
        if rc:
            raise AculabSpeechError(rc, 'sm_vmptx_generate_tones')

class VMP(RTPBase):
    """An RTP speech data transmitter/receiver.

    Combines a VMPtx and a VMPrx"""

    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):

        self.tx = self.rx = None
        self.tx = VMPtx(controller, card, module, mutex, user_data, ts_type,
                        reactor)

        self.rx = VMPrx(controller, card, module, mutex, user_data, ts_type,
                        reactor)

    def get_switch(self):
        """Return a unique identifier for switch card comparisons.
        Used by switching."""

        return self.tx.get_switch()

    def get_module(self):
        return self.tx.get_module()

    def listen_to(self, other):
        return self.tx.listen_to(other)

    def get_datafeed(self):
        return self.rx.get_datafeed()

class FMPrx(RTPBase):
    """An RTP T.38 receiver (untested/incomplete).

    Logging: output from a FMPrx is prefixed with C{frx-}"""

    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeData,
                 reactor = SpeechReactor):
        """Allocate an RTP FAX receiver, and add the event to the reactor.

        Note: the FMPrx is not ready to use until it has called 'fmprx_ready'
        on its controller.
        
        Controllers must implement:
         - fmprx_ready(vmprx, sdp, user_data)
         - fmprx_running(vmprx, user_data)
        """

        self.controller = controller
        self.reactor = reactor

        # initialize early
        self.vmprx = None
        self.event_fmprx = None
        self.datafeed = None
        self.rtp_port = None
        self.rtcp_port = None
        self.sdp = None

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)
        
        # create vmprx
        fmprx = lowlevel.SM_FMPRX_CREATE_PARMS()
        fmprx.module = self.module.open.module_id
        # vmprx.set_address(self.card.ip_address)
        rc = lowlevel.sm_fmprx_create(fmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmprx_create')

        self.fmprx = fmprx.fmprx

        self.name = 'frx-%08x' % self.fmprx

        # get the datafeed
        datafeed = lowlevel.SM_FMPRX_DATAFEED_PARMS()

        datafeed.fmprx = self.fmprx
        rc = lowlevel.sm_fmprx_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmprx_get_datafeed')

        self.datafeed = datafeed.datafeed

        # get the event
        efmprx = lowlevel.SM_FMPRX_EVENT_PARMS()
        efmprx.fmprx = self.fmprx

        rc = lowlevel.sm_fmprx_get_event(efmprx)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmprx_get_event')

        self.event_fmprx = add_event(self.reactor, efmprx.event, self.on_fmprx)
        
    def close(self):
        """Stop the receiver."""

        RTPBase.close(self)

        if self.fmprx:
            stopp = lowlevel.SM_FMPRX_STOP_PARMS()
            stopp.fmprx = self.fmprx

            rc = lowlevel.sm_fmprx_stop(stopp)
            if rc:
                raise AculabSpeechError(rc, 'sm_fmprx_stop')

            log.debug("%s stopping", self.name)

    def on_fmprx(self):
        """Internal event handler."""
        
        status = lowlevel.SM_FMPRX_STATUS_PARMS()
        status.fmprx = self.fmprx

        rc = lowlevel.sm_fmprx_status(status)
        log.debug('%s fmprx status: %s', self.name,
                  names.fmprx_status_names[status.status])
        
        if status.status == lowlevel.kSMFMPrxStatusGotPorts:
            self.rtp_port = status.u.ports.RTP_Port
            self.rtcp_port = status.u.ports.RTCP_Port
            self.address = status.get_address()
            # self.rtp_address = status.ports_address()
            log.debug('%s fmprx: rtp address: %s rtp port: %d, rtcp port: %d',
                      self.name, self.address, self.rtp_port, self.rtcp_port)
        
            self.controller.fmprx_ready(self, self.user_data)

        elif status.status == lowlevel.kSMFMPrxStatusStopped:
            self.reactor.remove(self.event_fmprx)
            self.event_fmprx = None
            self.datafeed = None
            
            rc = lowlevel.sm_fmprx_destroy(self.fmprx)
            self.fmprx = None

            if rc:
                raise AculabSpeechError(rc, 'sm_fmprx_destroy')

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def default_sdp(self):
        """Create a default SDP for T.38."""

        # The values are guesswork for now

        md = sdp.MediaDescription('image %d udptl t38' % self.rtp_port)
        md._a = { 'T38FaxVersion': (3,),
              'T38maxBitRate': (9600,),
              'T38FaxFillBitRemoval': (0,),
              'T38FaxTranscodingMMR': (0,),
              'T38FaxTranscodingJBIG': (0,),
              'T38FaxRateManagement': ('transferredTCF',),
              'T38FaxMaxBuffer': (284,),
              'T38FaxMaxDatagram': (128,0),
              'T38FaxUdpEC': ('t38UDPRedundancy',) }
        
        sd = sdp.SDP()
        sd.addMediaDescription(md)

        return sd
            
class FMPtx(RTPBase):
    """An RTP T.38 transmitter (untested/incomplete).

    Logging: output from a FMPrx is prefixed with C{frx-}"""

    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeData,
                 reactor = SpeechReactor):

        self.controller = controller
        self.reactor = reactor

        # initialize early 
        self.event_fmptx = None
        self.event_fmprx = None

        RTPBase.__init__(self, card, module, mutex, user_data, ts_type)

        # create fmptx
        fmptx = lowlevel.SM_FMPTX_CREATE_PARMS()
        fmptx.module = self.module.open.module_id
        rc = lowlevel.sm_fmptx_create(fmptx)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmptx_create')

        self.fmptx = fmptx.fmptx
        self.name = 'ftx-%08x' % self.fmptx

        efmptx = lowlevel.SM_FMPTX_EVENT_PARMS()
        efmptx.fmptx = self.fmptx

        rc = lowlevel.sm_fmptx_get_event(efmptx)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmptx_get_event')

        self.event_fmptx = add_event(self.reactor, efmptx.event, self.on_fmptx)

    def close(self):
        """Stop the transmitter."""

        RTPBase.close(self)

        if self.fmptx:
            stopp = lowlevel.SM_FMPTX_STOP_PARMS()
            stopp.fmptx = self.fmptx

            rc = lowlevel.sm_fmptx_stop(stopp)
            if rc:
                raise AculabSpeechError(rc, 'sm_fmptx_stop')

            log.debug("%s stopping", self.name)

    def __del__(self):
        self.close()

    def on_fmptx(self):
        status = lowlevel.SM_FMPTX_STATUS_PARMS()
        status.fmptx = self.fmptx

        rc = lowlevel.sm_fmptx_status(status)
        log.debug('%s fmptx status: %s', self.name,
                  names.fmptx_status_names[status.status])

        if status.status == lowlevel.kSMFMPtxStatusStopped:
            self.reactor.remove(self.event_fmptx)
            self.event_fmptx = None
            
            rc = lowlevel.sm_fmptx_destroy(self.fmptx)
            self.fmptx = None

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def configure(self, sdp):
        """Configure the Transmitter according to the SDP.

        @param sdp: An instance of class L{SDP}."""

        config = lowlevel.SM_FMPTX_CONFIG_PARMS()
        config.fmptx = self.fmptx
        addr = sdp.getAddress('image')

        log.debug('%s destination: %s', self.name, addr)
        
        config.set_destination(addr)
        config.RecoveryLevel = 1

        rc = lowlevel.sm_fmptx_config(config)
        if rc:
            raise AculabSpeechError(rc, 'sm_fmptx_config')

    def listen_to(self, other):
        """Listen to a timeslot or a tx instance.

        I{Switching protocol}. Applications should
        generally use L{switching.connect}.
        
        @param source: a tuple (stream, timeslot, [timeslot_type]) or a
        transmitter instance (L{VMPtx}, L{FMPtx} or L{TDMtx}), which must be on
        the same module."""

        if hasattr(other, 'get_datafeed'):
            connect = lowlevel.SM_FMPTX_DATAFEED_CONNECT_PARMS()
            connect.fmptx = self.fmptx
            connect.data_source = other.get_datafeed()

            rc = lowlevel.sm_fmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_fmptx_datafeed_connect')

            log_switch.debug('%s := %s', self.name, other.name)

            return FMPtxEndpoint(self)
        else:
            tdm = TDMrx(other, self.card, self.module)
            
            connect = lowlevel.SM_FMPTX_DATAFEED_CONNECT_PARMS()
            connect.fmptx = self.fmptx
            connect.data_source = tdm.get_datafeed()

            rc = lowlevel.sm_fmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_fmptx_datafeed_connect')

            log_switch.debug('%s := %s', self.name, other.name)

            return FMPtxEndpoint(self, tdm)

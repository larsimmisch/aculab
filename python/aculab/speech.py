"""Higher level speech processing functions.

This module contains the SpeechChannel, which is a full duplex prosody channel,
and higher level speech processing functions.

These higher level speech processing functions are internally represented as
jobs, but the job can be used explicitly to create, store or retrieve speech
operations.

The design goal is to encapsulate every speech operation as a job.
The only exception is DTMF recognition: this is always active and not
represented by a job."""

import sys
import os
import time
import logging
import lowlevel
import names
from util import Lockable
from fax import FaxRxJob
from reactor import SpeechReactor
from switching import Connection, CTBusEndpoint, SpeechEndpoint, DefaultBus
from util import swig_value, os_event
from error import *

__all__ = ['PlayJob', 'RecordJob', 'DigitsJob', 'SpeechChannel', 'version']

log = logging.getLogger('speech')
log_switch = logging.getLogger('switch')

# check driver info and create prosody streams if TiNG detected
_driver_info = lowlevel.SM_DRIVER_INFO_PARMS()
lowlevel.sm_get_driver_info(_driver_info)
version = (_driver_info.major, _driver_info.minor)
del _driver_info

def translate_card(card, module):
    if version[0] < 2:
        return card, module

    from snapshot import Snapshot

    if type(card) == type(0):
        c = Snapshot().prosody[card]
    else:
        c = card

    if type(module) == type(0):
        m = c.modules[module]
    else:
        m = module

    return c, m

class PlayJob(object):
    """A PlayJob plays a file through its L{SpeechChannel}."""

    def __init__(self, channel, f, agc = 0,
                 speed = 0, volume = 0):
        """Create a PlayJob.

        @param channel: The L{SpeechChannel} that will play the file.
        @param f: Either a filename (string) or a file descriptor.
        If a string is passed in, the associated file will be opened for
        playing and closed upon completion.
        If a fd is passed in, the file will be left open and not be reset
        to the beginning.
        @param agc: A nonzero value activates automatic gain control
        @param speed: The speed for used for replaying in percent. 0 is the
        same as 100: normal speed.
        @param volume: The volume adjustment in db.

        See U{sm_replay_start
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_replay_start.html>}
        for more information about the parameters.
        """
        
        self.channel = channel
        self.position = 0.0
        self.agc = agc
        self.speed = speed
        self.volume = volume

        # f may be a string - if it is, close self.file in done
        if type(f) == type(''):
            self.file = file(f, 'rb')
            self.filename = f
        else:
            self.file = f

        # read the length of the file
        self.file.seek(0, 2)
        
        # use a single buffer
        self.data = lowlevel.SM_TS_DATA_PARMS()
        self.length = self.file.tell()
        # Assumption: alaw or mulaw
        self.duration = self.length / 8000.0
        self.file.seek(0, 0)
        
    def start(self):
        """Start the playback.

        I{Do not call this method directly - call
        SpeechChannel.start(playjob) instead}
        """
        
        replay = lowlevel.SM_REPLAY_PARMS()
        replay.channel = self.channel.channel
        replay.agc = self.agc
        replay.speed = self.speed
        replay.volume = self.volume
        replay.type = lowlevel.kSMDataFormatALawPCM
        replay.sampling_rate = 8000
        replay.data_length = self.length

        rc = lowlevel.sm_replay_start(replay)
        if rc:
            raise AculabSpeechError(rc, 'sm_replay_start', self.channel.name)

        log.debug('%s play(%s, agc=%d, speed=%d, volume=%d, duration=%.3f)',
                  self.channel.name, str(self.file), self.agc,
                  self.speed, self.volume, self.duration)

        # On very short samples, we might be done after fill_play_buffer
        if not self.fill_play_buffer():
            # Ok. We are not finished yet.
            # Add a reactor to self and add the write event to it.
            self.reactor = self.channel.reactor
            self.reactor.add(os_event(self.channel.event_write),
                             self.fill_play_buffer)

        return self

    def done(self):
        """I{Used internally}."""
        
        # remove the write event from the reactor
        if self.reactor:
            self.reactor.remove(os_event(self.channel.event_write))

        # Compute reason.
        reason = None
        if self.position:
            reason = AculabStopped()
            pos = self.position
        else:
            pos = self.length

        # Assumption: alaw or mulaw
        self.duration = pos / 8000.0

        f = self.file

        if hasattr(self, 'filename'):
            f.close()
            self.file = None
            f = self.filename

        # no locks held - maybe too cautious
        log.debug('%s play_done(reason=\'%s\', duration=%.3f)',
                  self.channel.name, reason, self.duration)

        self.channel.job_done(self, 'play_done', reason, self.duration, f)

    def fill_play_buffer(self):
        """I{Used internally} to fill the play buffers on the board.
        
        @returns: True if completed"""
        
        status = lowlevel.SM_REPLAY_STATUS_PARMS()

        while True:
            status.channel = self.channel.channel

            rc = lowlevel.sm_replay_status(status)
            if rc:
                raise AculabSpeechError(rc, 'sm_replay_status',
                                        self.channel.name)

            # log.debug('%s replay status: %d', self.channel.name, status.status)

            if status.status in [lowlevel.kSMReplayStatusNoCapacity,
                                 lowlevel.kSMReplayStatusCompleteData]:
                return False
            elif status.status == lowlevel.kSMReplayStatusComplete:
                self.done()
                return True
            else:
                self.data.channel = self.channel.channel
                self.data.read(self.file)

                rc = lowlevel.sm_put_replay_data(self.data)
                if rc and rc != lowlevel.ERR_SM_NO_CAPACITY:
                    raise AculabSpeechError(rc, 'sm_put_replay_data',
                                            self.channel.name)

    def stop(self):
        """Stop a PlayJob. The internal position will be updated based upon
        the information available from the drivers."""

        stop = lowlevel.SM_REPLAY_ABORT_PARMS()
        stop.channel = self.channel.channel
        rc = lowlevel.sm_replay_abort(stop)
        if rc:
            raise AculabSpeechError(rc, 'sm_replay_abort', self.channel.name)

        # position is in seconds
        # Assumption: alaw/mulaw
        self.position = stop.offset / 8000.0

        log.debug('%s play_stop()', self.channel.name)

class RecordJob(object):
    """A RecordJob records a file through its L{SpeechChannel}."""
    
    def __init__(self, channel, f, max_octets = 0,
                 max_elapsed_time = 0.0, max_silence = 0.0, elimination = 0,
                 agc = 0, volume = 0):
        """Create a RecordJob. The recording will be in alaw, 8kHz.

        @param channel: The SpeechChannel that will do the recording.
        @param f: Either a string (filename) or a fd for the file.
        If a string is passed in, the associated file will be opened for
        recording and closed upon completion. If a fd is passed in,
        the file will be left open and not be reset to the beginning.
        @param max_octets: Maximum length of the recording (in bytes)
        @param max_silence: Maximum length of silence in seconds, before the
        recording is terminated.
        @param elimination: Activates silence elimination of not zero.
        @param agc: Nonzero values activate Automatic Gain Control        
        @param volume: The volume adjustment in db.

        See U{sm_record_start
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_record_start.html>}
        for more information about the parameters.        
        """

        self.channel = channel
        # f may be a string - if it is, close self.file in done
        if type(f) == type(''):
            self.file = file(f, 'wb')
            self.filename = f
        else:
            self.file = f

        self.data = lowlevel.SM_TS_DATA_PARMS()
        # size in seconds
        self.duration = 0.0
        self.max_octets = max_octets
        self.max_elapsed_time = max_elapsed_time
        self.max_silence = max_silence
        self.elimination = elimination
        self.agc = agc
        self.volume = volume
        self.reason = None

    def start(self):
        """Start the recording.

        I{Do not call this method directly - call SpeechChannel.start instead}
        """
        
        record = lowlevel.SM_RECORD_PARMS()
        record.channel = self.channel.channel
        record.type = lowlevel.kSMDataFormatALawPCM
        record.sampling_rate = 8000
        record.max_octets = self.max_octets
        record.max_elapsed_time = int(self.max_elapsed_time * 1000)
        record.max_silence = int(self.max_silence * 1000)
        record.elimination = self.elimination
        record.agc = self.agc
        record.volume = self.volume

        rc = lowlevel.sm_record_start(record)
        if rc:
            raise AculabSpeechError(rc, 'sm_record_start', self.channel.name)

        log.debug('%s record(%s, max_octets=%d, max_time=%.3f, '
                  'max_silence=%.3f, elimination=%d, agc=%d, volume=%d)',
                  self.channel.name, str(self.file), self.max_octets,
                  self.max_elapsed_time, self.max_silence, self.elimination,
                  self.agc, self.volume)
                  
        # add the read event to the reactor
        self.channel.reactor.add(os_event(self.channel.event_read),
                                 self.on_read)

    def done(self):                
        """Called internally upon completion."""
        
        # remove the read event from the reactor
        self.channel.reactor.remove(os_event(self.channel.event_read))

        channel = self.channel

        f = self.file
        if hasattr(self, 'filename'):
            self.file.close()
            self.file = None
            f = self.filename
        
        # no locks held - maybe too cautious
        log.debug('%s record_done(reason=\'%s\', length=%.3fs)',
                  channel.name, self.reason, self.duration)

        channel.job_done(self, 'record_done', self.reason, self.duration, f)
    
    def on_read(self):
        """Used internally, called whenever recorded data is available."""
        
        status = lowlevel.SM_RECORD_STATUS_PARMS()

        while True:
            status.channel = self.channel.channel

            rc = lowlevel.sm_record_status(status)
            if rc:
                self.reason = AculabSpeechError(rc, 'sm_record_status',
                                                self.channel.name)
                self.done()
                return

            if status.status == lowlevel.kSMRecordStatusComplete:
                if version[0] >= 2:
                    term = status.termination_reason
                    silence = status.termination_octets
                    # Todo check
                    rc = status.param0
                else:
                    how = lowlevel.SM_RECORD_HOW_TERMINATED_PARMS()
                    how.channel = self.channel.channel

                    rc = lowlevel.sm_record_how_terminated(how)
                    if rc:
                        raise AculabSpeechError(rc, 'sm_record_how_terminated',
                                                self.channel.name)

                    term = how.termination_reason
                    silence = how.termination_octets
                    rc = -1

                # Assumption: alaw/mulaw
                silence = silence / 8000.0
        
                self.reason = None
                if term == lowlevel.kSMRecordHowTerminatedLength:
                    self.reason = AculabTimeout()
                elif term == lowlevel.kSMRecordHowTerminatedMaxTime:
                    self.reason = AculabTimeout()
                elif term == lowlevel.kSMRecordHowTerminatedSilence:
                    self.reason = AculabSilence(silence)
                elif term == lowlevel.kSMRecordHowTerminatedAborted:
                    self.reason = AculabStopped()
                elif term == lowlevel.kSMRecordHowTerminatedError:
                    self.reason = AculabSpeechError(rc, 'RecordJob',
                                                    self.channel.name)
                    
                self.done()
                return
            elif status.status == lowlevel.kSMRecordStatusNoData:
                return
            else:
                self.data.channel = self.channel.channel
                self.data.length = lowlevel.kSMMaxRecordDataBufferSize

                rc = lowlevel.sm_get_recorded_data(self.data)
                if rc:
                    try:
                        self.stop()
                    finally:
                        self.reason = AculabSpeechError(
                            rc, 'sm_get_recorded_data', self.channel.name)
                    self.done()

                # Assumption: alaw/mulaw
                self.duration += self.data.length / 8000.0
                
                self.data.write(self.file)

    def stop(self):
        """Stop the recording."""
        
        abort = lowlevel.SM_RECORD_ABORT_PARMS()
        abort.channel = self.channel.channel
        rc = lowlevel.sm_record_abort(abort)
        if rc:
            raise AculabSpeechError(rc, 'sm_record_abort', self.channel.name)

        log.debug('%s record_stop()', self.channel.name)

class DigitsJob(object):
    """Job to play a string of DTMF digits."""
    
    def __init__(self, channel, digits, inter_digit_delay = 0,
                 digit_duration = 0):
        """Prepare to play a string of DTMF digits.

        @param digits: String of DTMF Digits. A digit can be from 0-9, A-D, *
        and #.
        @param inter_digit_delay: Delay between digits in B{milliseconds}. Zero
        for the default value (exact value unknown).
        @param digit_duration: Duration of each digit in B{milliseconds}. Zero
        for the default value (exact value unknown).

        See U{sm_play_digits
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_play_digits.html>}
        for more information about the parameters.

        Only C{kSMDTMFDigits} is supported as C{type}.
        """
        
        self.channel = channel
        self.digits = digits
        self.inter_digit_delay = inter_digit_delay
        self.digit_duration = digit_duration
        self.stopped = False

    def start(self):
        """Do not call this method directly - call L{SpeechChannel.start}
        instead."""
        
        dp = lowlevel.SM_PLAY_DIGITS_PARMS()
        dp.channel = self.channel.channel
        dp.digits.type = lowlevel.kSMDTMFDigits
        dp.digits.digit_string = self.digits
        dp.digits.inter_digit_delay = self.inter_digit_delay
        dp.digits.digit_duration = self.digit_duration

        rc = lowlevel.sm_play_digits(dp)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_digits', self.channel.name)

        log.debug('%s digits(%s, inter_digit_delay=%d, digit_duration=%d)',
                  self.channel.name, self.digits, self.inter_digit_delay,
                  self.digit_duration)

        # add the write event to the reactor
        self.channel.reactor.add(os_event(self.channel.event_write),
                                 self.on_write)

    def on_write(self):
        if self.channel is None:
            return
        
        status = lowlevel.SM_PLAY_DIGITS_STATUS_PARMS()
        status.channel = self.channel.channel

        rc = lowlevel.sm_play_digits_status(status)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_digits_status',
                                    self.channel.name)

        if status.status == lowlevel.kSMPlayDigitsStatusComplete:

            channel = self.channel
            
            reason = None
            if self.stopped:
                reason = AculabStopped()

            # remove the write event from to the reactor
            channel.reactor.remove(os_event(channel.event_write))

            log.debug('%s digits_done(reason=\'%s\')',
                      channel.name, reason)

            channel.job_done(self, 'digits_done', reason)
                
    def stop(self):
        """Stop the playing of digits."""
        
        self.stopped = True
        log.debug('%s digits_stop()', self.channel.name)

        # remove the write event from the reactor
        self.channel.reactor.remove(os_event(self.channel.event_write))

        # Position is only nonzero when play was stopped.
        channel = self.channel
        
        # Compute reason.
        reason = None
        if self.position:
            reason = AculabStopped()
            # Assumption: alaw or mulaw
            pos = self.position / 8000.0
        else:
            # Assumption: alaw or mulaw
            pos = self.length / 8000.0

        # no locks held - maybe too cautious
        log.debug('%s digits_done(reason=\'%s\', pos=%.3f)',
                  channel.name, reason, pos)

        channel.job_done(self, 'digits_done', reason) #, pos)

class DCReadJob(object):
    """A DataComms receive job."""
    
    def __init__(self, channel, cmd, min_to_collect, min_idle = 0,
                 blocking = 0):
        """Receive binary (possible modulated) data.

        See U{smdc_rx_control
        <http://www.aculab.com/support/TiNG/gen/apifn-smdc_rx_control.html>}
        for more information about the parameters.
        """
        
        self.channel = channel
        self.cmd = cmd
        self.min_to_collect = min_to_collect
        self.min_idle = min_idle
        self.blocking = blocking

    def start(self):
        'Do not call this method directly - call SpeechChannel.start instead'

        control = lowlevel.SMDC_RX_CONTROL_PARMS()

        control.channel = self.channel.channel
        control.cmd = self.cmd
        control.min_to_collect = self.min_to_collect
        control.min_idle = self.min_idle
        control.blocking = self.blocking

        # add the read event to the reactor
        self.channel.reactor.add(os_event(self.channel.event_read),
                                 self.on_read)

        rc = lowlevel.smdc_rx_control(control)
        if rc:
            raise AculabSpeechError(rc, 'smdc_rx_control', self.channel.name)

        log.debug('%s dc_rx_control(cmd=%d, min_to_collect=%d, ' \
                  'min_idle=%d, blocking=%d)',
                  self.channel.name, self.cmd, self.min_to_collect,
                  self.min_idle, self.blocking)

    def on_read(self):
        self.channel.controller.dc_read(self.channel)

    def stop(self):
        rc = lowlevel.smdc_stop(self.channel.channel)
        if rc:
            raise AculabSpeechError(rc, 'smdc_stop', self.channel.name)

        # remove the write event from the reactor
        self.channel.reactor.remove(os_event(self.channel.event_read))

        # Position is only nonzero when play was stopped.
        channel = self.channel
        
        # no locks held - maybe too cautious
        log.debug('%s dc_read stopped',
                  channel.name)

        channel.job_done(self, 'dc_read_done', f, reason, pos)

class SpeechChannel(Lockable):
    """A full duplex Prosody channel.

    DTMF detection is started by default."""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, reactor = SpeechReactor):
        """Allocate a full duplex Prosody channel.

        @param controller: This object will receive notifications about
        completed jobs. Controllers must implement:
         - play_done(self, channel, file, reason, position, user_data)
         - dtmf(self, channel, digit, user_data)
         - record_done(self, channel, file, reason, size, user_data)
         - digits_done(self, channel, reason, user_data).
        
        Reason is an exception or None (for normal termination).

        @param card: either a card offset or a L{snapshot.Card} instance.

        @param module: either the Prosody Sharc DSP offset or
        a L{snapshot.Module} instance.

        @param mutex: if not C{None}, this mutex will be acquired before any
        controller method is invoked and released as soon as it returns.

        @param user_data: The data associated with this channel. In MVC terms,
        this would be the I{model}. In most of the examples, this is a L{Glue}
        subclass.

        @param reactor: The reactor used to dispatch controller methods.
        By default, a single reactor is used for all channels.
        """

        Lockable.__init__(self, mutex)

        self.controller = controller
        self.reactor = reactor
        self.user_data = user_data
        self.job = None
        self.close_pending = None
        # initialize early 
        self.event_read = None
        self.event_write = None
        self.event_recog = None
        self.in_ts = None
        self.out_ts = None
        self.channel = None
        self.datafeed = None
        self.name = 'sc-0000'

        self.card, self.module = translate_card(card, module)

        alloc = lowlevel.SM_CHANNEL_ALLOC_PLACED_PARMS()
        alloc.type = lowlevel.kSMChannelTypeFullDuplex
        if version[0] >= 2:
            alloc.module = self.module.open.module_id
        else:
            alloc.module = self.module

        rc = lowlevel.sm_channel_alloc_placed(alloc)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_alloc_placed')

        self.channel = alloc.channel

        self.name = 'sc-%04x' % self.channel

        self.info = lowlevel.SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = lowlevel.sm_channel_info(self.info)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_info', self.name)

        # initialise our events
        self.event_read = self.set_event(lowlevel.kSMEventTypeReadData)
        self.event_write = self.set_event(lowlevel.kSMEventTypeWriteData)
        self.event_recog = self.set_event(lowlevel.kSMEventTypeRecog)

        if version[0] >= 2:
            self._ting_connect()
            log.debug('%s out: %d:%d, in: %d:%d card: %d',
                      self.name, self.info.ost, self.info.ots,
                      self.info.ist, self.info.its, self.info.card)

        self._listen()

        # add the recog event to the reactor
        self.reactor.add(os_event(self.event_recog), self.on_recog)

    def __del__(self):
        """Close the channel if it is still open."""
        self.close()
        if self.channel is None:
            log.debug('%s deleted', self.name)

    def _close(self):
        """Finalizes the shutdown of a speech channel.

        I{Do not use directly, use L{SpeechChannel.close}}."""

        if self.close_pending:
            return
        
        self.user_data = None
        self.lock()
        try:
            if self.event_read:
                lowlevel.smd_ev_free(self.event_read)
                self.event_read = None
            if self.event_write:
                lowlevel.smd_ev_free(self.event_write)
                self.event_write = None
            if self.event_recog:
                self.reactor.remove(os_event(self.event_recog))
                lowlevel.smd_ev_free(self.event_recog)
                self.event_recog = None

            if self.out_ts:
                # attribute out_ts implies attribute module
                self.module.timeslots.free(self.out_ts)
                self.out_ts = None

            if self.in_ts:
                # attribute in_ts implies attribute module
                self.module.timeslots.free(self.in_ts)
                self.in_ts = None

            if self.channel:
                rc = lowlevel.sm_channel_release(self.channel)
                if rc:
                    raise AculabSpeechError(rc, 'sm_channel_release',
                                            self.name)
                self.channel = None
        finally:
            self.unlock()
            if hasattr(self, 'name'):
                log.debug('%s closed', self.name)
            
##     def __cmp__(self, other):
##         return self.channel.__cmp__(other.channel)

##     def __hash__(self):
##         return self.channel

    def _ting_connect(self):
        """Connect the channel to a timeslot on its DSPs timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""

        # switch to local timeslots for TiNG
        if self.info.ost == -1:
            self.out_ts = self.module.timeslots.allocate()
            self.info.ost, self.info.ots = self.out_ts

            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st, output.ts = self.out_ts
                
            rc = lowlevel.sm_switch_channel_output(output)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_output',
                                        self.name)

            self.out_connection = SpeechEndpoint(self, 'out')

        if self.info.ist == -1:
            self.in_ts = self.module.timeslots.allocate()
            self.info.ist, self.info.its = self.in_ts

            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st, input.ts = self.in_ts

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input',
                                        self.name)
            
            self.in_connection = SpeechEndpoint(self, 'in')


    def _listen(self):
        """Start DTMF detection."""
        listen_for = lowlevel.SM_LISTEN_FOR_PARMS()
        listen_for.channel = self.channel
        listen_for.tone_detection_mode = \
                                  lowlevel.kSMToneDetectionMinDuration40;
        listen_for.map_tones_to_digits = lowlevel.kSMDTMFToneSetDigitMapping;
        rc = lowlevel.sm_listen_for(listen_for)
        if rc:
            raise AculabSpeechError(rc, 'sm_listen_for', self.name)

    def close(self):
        """Close the channel.

        If the channel is active, all pending jobs will be stopped before
        the channel is freed."""
        if self.job:
            self.lock()
            self.close_pending = True
            self.unlock()
            self.job.stop()
            return

        self._close()
        
    def set_event(self, _type):
        """Create and set an event for the channel.

        I{Used internally.}

        @param _type: One of:
         - lowlevel.kSMEventTypeReadData
         - lowlevel.kSMEventTypeWriteData
         - lowlevel.kSMEventTypeRecog
         """

        rc, handle = lowlevel.smd_ev_create(self.channel, _type,
                                            lowlevel.kSMChannelSpecificEvent)
        if rc:
            raise AculabSpeechError(rc, 'smd_ev_create', self.name)

        event = lowlevel.SM_CHANNEL_SET_EVENT_PARMS()

        event.channel = self.channel
        event.issue_events = lowlevel.kSMChannelSpecificEvent
        event.event_type = _type
        event.event = handle

        rc = lowlevel.sm_channel_set_event(event)
        if rc:
            lowlevel.smd_ev_free(event.handle)
            raise AculabSpeechError(rc, 'sm_channel_set_event', self.name)

        return handle

    def get_datafeed(self):
        """Get the datafeed."""

        if self.datafeed:
            return self.datafeed

        datafeed = lowlevel.SM_CHANNEL_DATAFEED_PARMS()
        datafeed.channel = self.channel

        rc = lowlevel.sm_channel_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_get_datafeed', self.name)

        self.datafeed = datafeed.datafeed
        
        return self.datafeed

    def listen_to(self, source):
        """Listen to a timeslot or a tx instance.
        
        @param source: a tuple (stream, timeslot) or a transmitter instance
            (VMPtx, FMPtx or TDMtx)"""

        if hasattr(source, 'get_datafeed'):
            connect = lowlevel.SM_CHANNEL_DATAFEED_CONNECT_PARMS()
            connect.channel = self.channel
            connect.data_source= source.get_datafeed()

            rc = lowlevel.sm_channel_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_channel_datafeed_connect',
                                        self.name)

            log_switch.debug('%s := %s', self.name, source.name)

            return SpeechEndpoint(self, 'datafeed')

        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st, input.ts = source

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input(%d:%d)' %
                                        (input.st, input.ts), self.name)

            log_switch.debug('%s := %d:%d', self.name,
                             source[0], source[1])

            return SpeechEndpoint(self, 'in')
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost = self.info.ist		# sink
        output.ots = self.info.its
        output.mode = lowlevel.CONNECT_MODE
        output.ist, output.its = source

        rc = lowlevel.sw_set_output(self.card.card_id, output)
        if (rc):
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusEndpoint(self.card.card_id,
                             (self.info.ist, self.info.its))

    def speak_to(self, sink):
        """Speak to a timeslot.

        @param sink: a tuple (stream, timeslot)."""

        if self.info.card == -1:
            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st, output.ts = sink

            rc = lowlevel.sm_switch_channel_output(output)
            if rc:
                return AculabSpeechError(
                    rc, 'sm_switch_channel_output(%d:%d)' %
                    (output.st, output.ts), self.name)

            log_switch.debug('%s speak_to(%d:%d)', self.name,
                             sink[0], sink[1])

            return SpeechEndpoint(self, 'out')
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost, output.ots = sink       # sink
        output.mode = lowlevel.CONNECT_MODE
        output.ist = self.info.ost			# source
        output.its = self.info.ots

        rc = lowlevel.sw_set_output(self.card.card_id, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusEndpoint(self.card.card_id, sink)

    def dc_config(self, protocol, pconf, encoding, econf):
        """Configure the channel for data communications.

        See U{smdc_channel_config
        <http://www.aculab.com/support/TiNG/gen/apifn-smdc_channel_config.html>}
        for more information about the parameters.

        """
        
        config = lowlevel.SMDC_CHANNEL_CONFIG_PARMS()
        config.channel = self.channel
        config.protocol = protocol
        config.config_length = 0
        if pconf:
            config.config_length = len(pconf)
        config.config_data = pconf
        config.encoding = encoding
        config.encoding_config_length = 0
        if econf:
            config.encoding_config_length = 8 # len(econf)
        config.encoding_config_data = econf

        rc = lowlevel.smdc_channel_config(config)
        if rc:
            raise AculabSpeechError(rc, 'smdc_channel_config', self.name)

    def start(self, job):
        """Start a job.

        Only a single job may run at the same time. This is somewhat arbitrary
        limitation that merely simplifies the implementation."""
        if self.job:
            raise RuntimeError('Already executing job')

        if not self.close_pending:
            self.job = job
            job.start()
    
    def play(self, file, volume = 0, agc = 0, speed = 0):
        """Play an file.

        This is a shorthand to create and start a L{PlayJob}."""

        job = PlayJob(self, file, agc, volume, speed)

        self.start(job)

    def record(self, file, max_octets = 0,
               max_elapsed_time = 0.0, max_silence = 0.0, elimination = 0,
               agc = 0, volume = 0):
        """Record to an alaw file.

        This is a shorthand to create and starts a L{RecordJob}."""

        job = RecordJob(self, file, max_octets,
                        max_elapsed_time, max_silence, elimination,
                        agc, volume)

        self.start(job)

    def digits(self, digits, inter_digit_delay = 0, digit_duration = 0):
        """Send a string of DTMF digits."""

        job = DigitsJob(self, digits, inter_digit_delay,
                        digit_duration)

        self.start(job)

    def faxrx(self, file, subscriber_id = ''):
        """Receive a FAX asynchronously."""

        job = FaxRxJob(self, file, subscriber_id)

        self.start(job)        

    def faxtx(self, file, subscriber_id = ''):
        """Transmit a FAX asynchronously."""

        job = FaxTxJob(self, file, subscriber_id)

        self.start(job)        

    def on_recog(self):
        # log.debug('%s on_recog', self.name)
        recog = lowlevel.SM_RECOGNISED_PARMS()
        
        while True:
            recog.channel = self.channel

            rc = lowlevel.sm_get_recognised(recog)
            if rc:
                raise AculabSpeechError(rc, 'sm_get_recognised', self.name)

            if recog.type == lowlevel.kSMRecognisedNothing:
                return
            elif recog.type == lowlevel.kSMRecognisedDigit:
                self.lock()
                try:
                    self.controller.dtmf(self, chr(recog.param0),
                                         self.user_data)
                finally:
                    self.unlock()
            
    def stop(self):
        if self.job:
            self.job.stop()

    def job_done(self, job, fn, reason, *args, **kwargs):
        args = args + (self.user_data,)

        self.lock()
        self.job = None
        if self.close_pending:
            self.close()
        self.unlock()

        f = getattr(self.controller, fn)
        f(self, reason, *args, **kwargs)
        m = getattr(self.controller, 'job_done', None)
        if m:
            m(job, reason, self.user_data)

class Conference(Lockable):
    """A Conference: not fully implemented yet."""

    def __init__(self, module = None, mutex = None):
        Lockable.__init__(self, mutex)
        
        self.module = module
        self.listeners = 0
        self.speakers = 0
        self.mutex = mutex

    def add(self, channel, mode):
        self.lock()
        try:
            pass
        finally:
            self.unlock()

    def remove(self, channel):
        self.lock()
        try:
            pass
        finally:
            self.unlock()

if version[0] >= 2:

    class TDMtx(object):
        def __init__(self, controller, ts,
                     ts_type = lowlevel.kSMTimeslotTypeALaw,
                     card = 0, module = 0):
            """Create a TDM transmitter.
            
            See U{sm_tdmtx_create
            <http://www.aculab.com/support/TiNG/gen/\
            apifn-sm_tdmtx_create.html>}.
            """
            
            self.card, self.module = translate_card(card, module)
            self.user_data = user_data

            tdmtx = lowlevel.SM_TDMTX_CREATE_PARMS()
            tdmtx.module = self.module.open.module_id
            tdmtx.stream = ts[0]
            tdmtx.timeslot = ts[1]
            tdmtx.type = ts_type

            rc = lowlevel.sm_tdmtx_create(tdmtx)
            if rc:
                raise AculabSpeechError(rc, 'sm_tdmtx_create')
                
            self.tdmtx = tdmtx.tdmtx

        def close(self):
            if self.tdmtx:
                rc = lowlevel.smd_tdmtx_destroy(self.tdmtx)
                self.tdmtx = None

        def listen_to(self, other):
            if hasattr(other, 'get_datafeed'):
                connect = lowlevel.SM_TDMTX_DATAFEED_CONNECT_PARMS()
                connect.tdmtx = self.tdmtx
                connect.data_source = other.get_datafeed()

                rc = lowlevel.sm_tdmtx_datafeed_connect(connect)
                if rc:
                    raise AculabSpeechError(
                        rc, 'sm_tdmtx_datafeed_connect', self.name)

                log_switch.debug('%s := %s', self.name, other.name)
            else:
                raise ValueError('Cannot connect to instance without '\
                                 'get_datafeed() method')
            
    class TDMrx(object):
        def __init__(self, controller, ts,
                     ts_type = lowlevel.kSMTimeslotTypeALaw,
                     card = 0, module = 0):
            """Create a TDM transmitter.
            
            See U{sm_tdmrx_create
            <http://www.aculab.com/support/TiNG/gen/\
            apifn-sm_tdmrx_create.html>}.
            """
            
            self.card, self.module = translate_card(card, module)
            self.user_data = user_data
            # Initialize early
            self.tdmrx = None
            self.datafeed = None

            tdmrx = lowlevel.SM_TDMTX_CREATE_PARMS()
            tdmrx.module = self.module.open.module_id
            tdmrx.stream = ts[0]
            tdmrx.timeslot = ts[1]
            tdmrx.type = ts_type

            rc = lowlevel.sm_tdmrx_create(tdmrx)
            if rc:
                raise AculabSpeechError(rc, 'sm_tdmrx_create')
                
            self.tdmrx = tdmrx.tdmrx

            # get the datafeed
            datafeed = lowlevel.SM_TDMRX_DATAFEED_PARMS()

            datafeed.tdmrx = self.tdmrx
            rc = lowlevel.sm_tdmrx_get_datafeed(datafeed)
            if rc:
                raise AculabSpeechError(rc, 'sm_tdmrx_get_datafeed', self.name)

            self.datafeed = datafeed.datafeed

        def close(self):
            if self.tdmrx:
                rc = lowlevel.smd_tdmrx_destroy(self.tdmrx)
                self.datafeed = None
                self.tdmrx = None

        def get_datafeed(self):
            """Used internally by the switching protocol."""
            return self.datafeed


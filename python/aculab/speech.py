# Copyright (C) 2002-2008 Lars Immisch

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
import select
from util import Lockable, translate_card
from fax import FaxRxJob, FaxTxJob
from reactor import SpeechReactor
from switching import (Connection, CTBusEndpoint, SpeechEndpoint, TDMrx, TDMtx,
                       DefaultBus, connect)
from util import TiNG_version
from error import *

__all__ = ['PlayJob', 'RecordJob', 'DigitsJob', 'ToneJob', 'SilenceJob',
           'SpeechChannel', 'Conference', 'Glue']

log = logging.getLogger('speech')
log_switch = logging.getLogger('switch')

def guess_filetype(fn):
    ext = os.path.splitext(fn)[1]
    if ext == '.al':
        return (lowlevel.kSMDataFormatALawPCM, 8000, 8000)
    elif ext == '.ul':
        return (lowlevel.kSMDataFormatULawPCM, 8000, 8000)
    elif ext == '.sw':
        return (lowlevel.kSMDataFormat16bit, 8000, 16000)

    return (lowlevel.kSMDataFormatALawPCM, 8000, 8000)

tonetype = { lowlevel.kSMRecognisedNothing: 'nothing',
             lowlevel.kSMRecognisedTrainingDigit: 'training digit',
             lowlevel.kSMRecognisedDigit: 'digit',
             lowlevel.kSMRecognisedTone: 'tone',
             lowlevel.kSMRecognisedCPTone: 'call progress tone',
             lowlevel.kSMRecognisedGruntStart: 'grunt start',
             lowlevel.kSMRecognisedGruntEnd: 'grunt end',
             lowlevel.kSMRecognisedASRResult: 'asr result',
             lowlevel.kSMRecognisedASRUncertain: 'asr uncertain',
             lowlevel.kSMRecognisedASRRejected: 'asr rejected',
             lowlevel.kSMRecognisedASRTimeout: 'asr timeout',
             lowlevel.kSMRecognisedCatSig: 'cat sig',
             lowlevel.kSMRecognisedOverrun: 'overrun' }

if TiNG_version[0] >= 2:
    tonetype[lowlevel.kSMRecognisedANS] = 'ans'

class PlayJobBase(object):
    """An Abstract Base Class for playing samples through a L{SpeechChannel}.

    Subclasses must override C{get_data(len)}. C{get_data} must fill
    the buffer C{self.data} and return the length of the data.

    They must also override and call C{done} on this class for internal
    bookkeeping and it is the subclasses responsibility to call
    C{channel.job_done()} in C{done}.

    If subclasses have an attribute C{name} is present, it will be used for
    logging.
    """

    # Used for debug output
    name = 'play_base'
    
    def __init__(self, channel, agc = 0, speed = 0, volume = 0,
                 filetype = None):
        """Create an abstract PlayJob.

        @param channel: The L{SpeechChannel} that will play the file.
        @param agc: A nonzero value activates automatic gain control
        @param speed: The speed for used for replaying in percent. 0 is the
        same as 100: normal speed.
        @param volume: The volume adjustment in db.
        @param filetype: The file type. The default is C{kSMDataFormatALawPCM}.
        
        The sampling rate is hardcoded to 8000.

        See U{sm_replay_start
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_replay_start.html>}
        for more information about the parameters.
        """
        
        self.channel = channel
        self.position = 0.0
        self.agc = agc
        self.speed = speed
        self.volume = volume
        self.filetype = filetype
        self.sampling_rate = 8000
        self.data_rate = 8000
        # Bytes submitted so far
        self.offset = 0
        # The offset where the hardware stopped
        self.stop_offset = 0

        if filetype is None:
            self.filetype = lowlevel.kSMDataFormatALawPCM

        # use a single buffer
        self.data = lowlevel.SM_TS_DATA_PARMS()

    def start(self):
        """I{Generic job interface method}.

        Start playback.

        Applications should call L{SpeechChannel.play} or L
        {SpeechChannel.start}
        """
        
        replay = lowlevel.SM_REPLAY_PARMS()
        replay.channel = self.channel.channel
        replay.agc = self.agc
        replay.speed = self.speed
        replay.volume = self.volume
        replay.type = self.filetype
        if TiNG_version[0] >= 2:
            replay.sampling_rate = self.sampling_rate

        rc = lowlevel.sm_replay_start(replay)
        if rc:
            raise AculabSpeechError(rc, 'sm_replay_start', self.channel.name)

        if hasattr(self, 'datadesc'):
            log.debug('%s %s(%s, agc=%d, speed=%d, volume=%d)',
                      self.channel.name, self.name, self.datadesc, self.agc,
                      self.speed, self.volume)
        else:
            log.debug('%s %s(agc=%d, speed=%d, volume=%d)',
                      self.channel.name, self.name, self.agc,
                      self.speed, self.volume)

        # On very short samples, we might be done after fill_play_buffer
        if not self.fill_play_buffer():
            # Ok. We are not finished yet.
            # Add a reactor to self and add the write event to it.
            self.reactor = self.channel.reactor
            self.reactor.add(self.channel.event_write, self.fill_play_buffer)

        return self

    def done(self):
        """I{Generic job interface method}.

        Must be overwritten and called in subclasses when the job is complete.

        @return: a tuple (reason, duration). Duration is in seconds.
        """
        
        # remove the write event from the reactor
        if self.reactor:
            self.reactor.remove(self.channel.event_write)
            
        # Compute reason.
        reason = None
        if self.stop_offset:
            reason = AculabStopped()
            duration = float(self.stop_offset) / self.data_rate
        else:
            duration = float(self.offset) / self.data_rate

        log.debug('%s %s_done(reason=\'%s\', duration=%.3f)',
                  self.channel.name, self.name, reason, duration)

        return reason, duration

    def fill_play_buffer(self):
        """I{Reactor callback} - fills the play buffers on the board.
        
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
                l = self.get_data(lowlevel.kSMMaxReplayDataBufferSize)
                self.data.channel = self.channel.channel

                if l == lowlevel.kSMMaxReplayDataBufferSize:
                    rc = lowlevel.sm_put_replay_data(self.data)
                else:
                    rc = lowlevel.sm_put_last_replay_data(self.data)

                if rc:
                    raise AculabSpeechError(rc, 'sm_put_replay_data',
                                            self.channel.name)

                self.offset = self.offset + l

    def stop(self):
        """I{Generic job interface method}.

        Stops the PlayJob.

        Applications should call L{SpeechChannel.stop}.

        The internal position C{stop_offset} will be updated with
        the information from the driver."""

        stop = lowlevel.SM_REPLAY_ABORT_PARMS()
        stop.channel = self.channel.channel
        rc = lowlevel.sm_replay_abort(stop)
        if rc:
            raise AculabSpeechError(rc, 'sm_replay_abort', self.channel.name)

        # position is in seconds
        # Assumption: PCM
        self.stop_offset = stop.offset

        log.debug('%s %s_stop()', self.channel.name, self.name)


class PlayJob(PlayJobBase):
    """A PlayJob plays a file through its L{SpeechChannel}."""

    name = 'play'

    def __init__(self, channel, f, agc = 0, speed = 0, volume = 0,
                 filetype = None):
        """Create a PlayJob.

        See U{sm_replay_start
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_replay_start.html>}
        for more information about the parameters.

        See also L{SpeechChannel.play}.

        The sampling rate is currently hardcoded to 8000.
        
        @param channel: The L{SpeechChannel} that will play the file.
        @param f: Either a filename (string) or a file descriptor.
        If a string is passed in, the associated file will be opened for
        playing and closed upon completion. Filename extensions will be
        treated as a hint for the file type, but only if filetype is not
        C{None}. Currently recognized filename extensions are C{.al}, C{.ul}
        and C{sw}.
        If a file descriptor d is passed in, the file will be left open (and
        the file pointer will be left at the position where the replay
        stopped).
        @param agc: A nonzero value activates automatic gain control
        @param speed: The speed for used for replaying in percent. 0 is the
        same as 100: normal speed.
        @param volume: The volume adjustment in db.
        @param filetype: The file type. The default is C{kSMDataFormatALawPCM}.
        """

        PlayJobBase.__init__(self, channel, agc, speed, volume, filetype)
        
        # f may be a string - if it is, close self.file in done
        if type(f) == type(''):
            self.file = file(f, 'rb')
            self.filename = f
            if filetype is None:
                self.filetype, self.sampling_rate, self.data_rate = \
                               guess_filetype(f)
        else:
            self.file = f
            if filetype is None:
                self.filetype = lowlevel.kSMDataFormatALawPCM

        # read the length of the file
        pos = self.file.tell()
        self.file.seek(0, 2)
        self.length = self.file.tell() - pos
        self.file.seek(pos, 0)

        # used for logging
        self.datadesc = str(self.file)
        
    def done(self):
        """I{Generic job interface method}."""

        reason, duration = PlayJobBase.done(self)
        
        f = self.file

        if hasattr(self, 'filename'):
            f.close()
            self.file = None
            f = self.filename

        self.channel.job_done(self, 'play_done', reason, duration, f)

    def get_data(self, length):
        """I{PlayJobBase interface method}."""
                
        return self.data.read(self.file, length)

class SilenceJob(PlayJobBase):
    """Play silence on a L{SpeechChannel}."""

    name = 'silence'

    def __init__(self, channel, duration = 0.0):
        """Create a SilenceJob.

        @param channel: The L{SpeechChannel} that will play silence.
        @param duration: The length of the silence in seconds.
        """

        PlayJobBase.__init__(self, channel)

        # Work with ms internally
        self.duration = int(duration * self.data_rate)
        
    def done(self):
        """I{Generic job interface method}."""

        reason, duration = PlayJobBase.done(self)
        
        self.channel.job_done(self, 'silence_done', reason, duration)

    def get_data(self, length):
        """I{PlayJobBase interface method}."""

        r = self.duration - self.offset 
        if r < length:
            length = r

        # alaw silence, as our filetype is alaw by default
        # we could look at the ts_type of the channel for a possible
        # optimisation
        self.data.setdata('\x55' * length)
        return length


class RecordJob(object):
    """A RecordJob records a file through its L{SpeechChannel}."""
    
    def __init__(self, channel, f, max_octets = 0,
                 max_elapsed_time = 0.0, max_silence = 0.0,
                 elimination = False, agc = False, volume = 0,
                 filetype = None):
        """Create a RecordJob.

        The sampling rate is currently hardcoded to 8000.

        See U{sm_record_start
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_record_start.html>}
        for more information about the parameters.

        See also L{SpeechChannel.record}.
        
        @param channel: The SpeechChannel that will do the recording.
        @param f: Either a string (filename) or a fd for the file.
        If a string is passed in, the associated file will be opened for
        recording and closed upon completion. Filename extensions will be
        treated as a hint for the file type, but only if filetype is not
        C{None}. Currently recognized filename extensions are C{.al}, C{.ul}
        and C{.sw}.
        If a fd is passed in, the file will be left open and not be reset
        to the beginning.
        @param max_octets: Maximum length of the recording (in bytes)
        @param max_elapsed_time: Maximum length the recording in seconds.
        @param max_silence: Maximum length of silence in seconds, before the
        recording is terminated.
        @param elimination: Activates silence elimination if not zero.
        @param agc: Nonzero values activate Automatic Gain Control        
        @param volume: The volume adjustment in db.
        @param filetype: The file type. If no type can be deduced from the
        filename, C{kSMDataFormatALawPCM} will be used.
        """

        self.channel = channel
        self.filetype = filetype
        self.data_rate = 8000
        self.sampling_rate = 8000
        # f may be a string - if it is, close self.file in done
        if type(f) == type(''):
            self.file = file(f, 'wb')
            self.filename = f
            if filetype is None:
                self.filetype, self.sampling_rate, self.data_rate = \
                               guess_filetype(f)
        else:
            self.file = f
            if filetype is None:
                self.filetype = lowlevel.kSMDataFormatALawPCM

        self.data = lowlevel.SM_TS_DATA_PARMS(
            lowlevel.kSMMaxRecordDataBufferSize)
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
        """I{Generic job interface method}

        Start the recording.

        Applications should use L{SpeechChannel.record} or
        L{SpeechChannel.start}.
        """
        
        record = lowlevel.SM_RECORD_PARMS()
        record.channel = self.channel.channel
        record.type = self.filetype
        record.max_octets = self.max_octets
        record.max_elapsed_time = int(self.max_elapsed_time * 1000)
        record.max_silence = int(self.max_silence * 1000)
        if TiNG_version[0] < 2:
            record.elimination = self.elimination
        else:
            # We abuse the fact that False == kSMToneDetectionNone
            record.tone_elimination_mode = self.elimination
            record.sampling_rate = self.sampling_rate
            
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
        self.channel.reactor.add(self.channel.event_read, self.on_read)

    def done(self):                
        """I{Generic job interface method}."""
        
        # remove the read event from the reactor
        self.channel.reactor.remove(self.channel.event_read)

        channel = self.channel

        f = self.file
        if hasattr(self, 'filename'):
            self.file.close()
            self.file = None
            f = self.filename
        
        log.debug('%s record_done(reason=\'%s\', length=%.3fs)',
                  channel.name, self.reason, self.duration)

        channel.job_done(self, 'record_done', self.reason, self.duration, f)
    
    def on_read(self):
        """I{Reactor callback},

        Called whenever recorded data is available."""
        
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
                if TiNG_version[0] >= 2:
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

                silence = silence / float(self.data_rate)
        
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

                self.duration += self.data.length / float(self.data_rate)
                
                self.data.write(self.file)

    def stop(self):
        """I{Generic job interface method}.

        Stop the recording.

        Applications should use L{SpeechChannel.stop} to stop a pending job.
        """
        
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

        See U{sm_play_digits
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_play_digits.html>}
        for more information about the parameters. I{Only C{kSMDTMFDigits} is
        supported as C{type}}.

        See also L{SpeechChannel.digits}.

        @param digits: String of DTMF Digits. A digit can be from 0-9, A-D, *
        and #.
        @param inter_digit_delay: Delay between digits in B{milliseconds}. Zero
        for the default value (exact value unknown).
        @param digit_duration: Duration of each digit in B{milliseconds}. Zero
        for the default value (exact value unknown).
        """
        
        self.channel = channel
        self.digits = digits
        self.inter_digit_delay = inter_digit_delay
        self.digit_duration = digit_duration
        self.stopped = False

    def start(self):
        """I{Generic job interface method}.

        Applications should use L{SpeechChannel.digits} or
        L{SpeechChannel.start}."""
        
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
        self.channel.reactor.add(self.channel.event_write, self.on_write)

    def on_write(self):
        """I{Reactor callback}."""
        
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
            channel.reactor.remove(channel.event_write)

            log.debug('%s digits_done(reason=\'%s\')',
                      channel.name, reason)

            channel.job_done(self, 'digits_done', reason)
                
    def stop(self):
        """I{Generic job interface method}."""
        
        self.stopped = True
        log.debug('%s digits_stop()', self.channel.name)

        # remove the write event from the reactor
        self.channel.reactor.remove(self.channel.event_write)

        # Position is only nonzero when play was stopped.
        channel = self.channel
        
        # Compute reason.
        reason = None

        # no locks held
        log.debug('%s digits_done(reason=\'%s\')',
                  channel.name, reason)

        channel.job_done(self, 'digits_done', reason) #, pos)


class ToneJob(object):
    """Job to play a predefined Tone."""
    
    def __init__(self, channel, tone, duration = 0.0):
        """Prepare to play a list of tones.

        See U{sm_play_tone
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_play_tone.html>}
        for more information about the parameters.

        See also L{SpeechChannel.tones}.

        @param tone: A predefined tone id.
        See the U{list of pre-loaded output tones
        <http://www.aculab.com/support/TiNG/prospapi_outtones.html>} for
        valid tone ids. Duration is in seconds, not milliseconds.
        0.0 is infinite.

        @param duration: the duration in seconds (float).
        """
        
        self.channel = channel
        self.tone = tone
        self.duration = duration

    def start(self):
        """I{Generic job interface method}.

        Applications should call L{SpeechChannel.tones} or
        L{SpeechChannel.start}."""

        tp = lowlevel.SM_PLAY_TONE_PARMS()
        tp.channel = self.channel.channel
        tp.tone_id = self.tone
        tp.duration = int(self.duration * 1000)

        rc = lowlevel.sm_play_tone(tp)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_tone', self.channel.name)

        log.debug('%s tone(%d, duration=%.3f)',
                  self.channel.name, self.tone, self.duration)

        # add the write event to the reactor
        self.channel.reactor.add(self.channel.event_write, self.on_write)

    def on_write(self):
        """I{Reactor callback}."""
        
        if self.channel is None:
            return
        
        status = lowlevel.SM_PLAY_TONE_STATUS_PARMS()
        status.channel = self.channel.channel

        rc = lowlevel.sm_play_tone_status(status)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_tone_status',
                                    self.channel.name)

        if status.status == lowlevel.kSMPlayToneStatusComplete:

            channel = self.channel
            reason = None

            # remove the write event from to the reactor
            channel.reactor.remove(channel.event_write)
            
            log.debug('%s tone_done(reason=\'%s\')',
                      channel.name, reason)
            
            channel.job_done(self, 'tone_done', reason)
                
    def stop(self):
        """I{Generic job interface}."""
        
        self.stopped = True
        log.debug('%s tone_stop()', self.channel.name)

        rc = lowlevel.sm_play_tone_abort(self.channel.channel)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_tone_abort',
                                    self.channel.name)

        # remove the write event from the reactor
        self.channel.reactor.remove(self.channel.event_write)

        channel = self.channel
        
        # Compute reason
        reason = AculabStopped()

        log.debug('%s tone_done(reason=\'%s\'', channel.name, reason)

        channel.job_done(self, 'digits_done', reason) #, pos)

class DCReadJob(object):
    """A DataComms receive job - experimental"""
    
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
        """I{Generic job interface}.

        Applications should call L{SpeechChannel.start}
        """

        control = lowlevel.SMDC_RX_CONTROL_PARMS()

        control.channel = self.channel.channel
        control.cmd = self.cmd
        control.min_to_collect = self.min_to_collect
        control.min_idle = self.min_idle
        control.blocking = self.blocking

        # add the read event to the reactor
        self.channel.reactor.add(self.channel.event_read, self.on_read)

        rc = lowlevel.smdc_rx_control(control)
        if rc:
            raise AculabSpeechError(rc, 'smdc_rx_control', self.channel.name)

        log.debug('%s dc_rx_control(cmd=%d, min_to_collect=%d, ' \
                  'min_idle=%d, blocking=%d)',
                  self.channel.name, self.cmd, self.min_to_collect,
                  self.min_idle, self.blocking)

    def on_read(self):
        """I{Reactor callback}."""
        
        self.channel.controller.dc_read(self.channel)

    def stop(self):
        """I{Generic job interface}.

        Applications should call L{SpeechChannel.stop}."""
        
        rc = lowlevel.smdc_stop(self.channel.channel)
        if rc:
            raise AculabSpeechError(rc, 'smdc_stop', self.channel.name)

        # remove the write event from the reactor
        self.channel.reactor.remove(self.channel.event_read)

        # Position is only nonzero when play was stopped.
        channel = self.channel
        
        # no locks held
        log.debug('%s dc_read stopped',
                  channel.name)

        channel.job_done(self, 'dc_read_done', f, reason, pos)

class SpeechChannel(Lockable):
    """A full duplex Prosody channel.

    Logging: a SpeechChannel instance name is prefixed with C{sc-}.
    The I{log name} is C{speech}."""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, ts_type = lowlevel.kSMTimeslotTypeALaw,
                 reactor = SpeechReactor):
        """Allocate a full duplex Prosody channel.

        @param controller: This object will receive notifications about
        completed jobs. Controllers must implement:
         - play_done(self, channel, reason, file, duration, user_data)
         - dtmf(self, channel, digit, user_data)
         - record_done(self, channel, reason, file, size, user_data)
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

        @param ts_type: The encoding to use on the timeslot, either alaw, mulaw
        or raw data. See U{sm_config_module_switching
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_config_module_switching.html>}
        for more details.

        @param reactor: The reactor used to dispatch controller methods.
        By default, a single reactor is used for all channels.
        """

        Lockable.__init__(self, mutex)

        self.controller = controller
        self.reactor = reactor
        self.user_data = user_data
        self.job = None
        self.close_pending = None
        self.tone_set_id = None
        self.tone_detection_mode = None
        self.ts_type = ts_type
        # initialize early 
        self.event_read = None
        self.event_write = None
        self.event_recog = None
        self.tdm = None
        self.channel = None
        self.datafeed = None
        self.name = 'sc-0000'
        self.close_queue = None

        self.card, self.module = translate_card(card, module)

        alloc = lowlevel.SM_CHANNEL_ALLOC_PLACED_PARMS()
        alloc.type = lowlevel.kSMChannelTypeFullDuplex
        if TiNG_version[0] >= 2:
            alloc.module = self.module.open.module_id
        else:
            alloc.module = self.module

        rc = lowlevel.sm_channel_alloc_placed(alloc)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_alloc_placed')

        self.channel = alloc.channel

        self.name = 'sc-%04x' % self.channel

        # log.debug('%s allocated', self.name)

        self.info = lowlevel.SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = lowlevel.sm_channel_info(self.info)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_info', self.name)

        # initialise our events
        self.event_read = self.set_event(lowlevel.kSMEventTypeReadData)
        self.event_write = self.set_event(lowlevel.kSMEventTypeWriteData)

    def __del__(self):
        """Close the channel if it is still open."""
        if self.channel is None:
            log.debug('%s deleted', self.name)
        else:
            self.close()

    def _close(self):
        """Finalizes the shutdown of a speech channel.

        I{Do not use directly, use L{SpeechChannel.close}}."""

        self.user_data = None
        self.lock()
        try:
            if self.tdm:
                self.tdm.close()
                self.tdm = None

            if self.event_read:
                lowlevel.smd_ev_free(self.event_read)
                self.event_read = None
            if self.event_write:
                lowlevel.smd_ev_free(self.event_write)
                self.event_write = None
            if self.event_recog:
                self.reactor.remove(self.event_recog)
                lowlevel.smd_ev_free(self.event_recog)
                self.event_recog = None

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

        if self.close_queue:
            for c in self.close_queue:
                c.close()

        self.close_queue = None

    def close(self, *args):
        """Close the channel.

        If the channel is active, all pending jobs will be stopped before
        the channel is freed.

        @param *args: this can be a list of VMPs, FMPs TDMs, Connections
        or Calls that will be closed when the channel is idle.
        The Fax-Libraries in particular will gladly dump core when
        VMPs or FMPs are closed before the job is finished.
        """

        if self.close_pending or self.close_queue:
            raise RuntimeError, "SpeechChannel is already stopping"

        self.close_queue = args
        
        if self.job:
            self.lock()
            self.close_pending = True
            self.unlock()
            self.job.stop()
            return

        self._close()
                    
##     def __cmp__(self, other):
##         return self.channel.__cmp__(other.channel)

##     def __hash__(self):
##         return self.channel

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

    def tdm_connect(self):
        """Connect the channel to a timeslot on its DSP's timeslot range.

        See L{ProsodyTimeslots}.

        I{Used internally}."""

        # switch to local timeslots for TiNG
        if self.info.ost == -1 or self.info.ist == -1:
            self.tdm = Connection(self.module.timeslots)
            
            tx = self.module.timeslots.allocate(self.ts_type)
            self.info.ost = tx[0]
            self.info.ots = tx[1]

            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st = tx[0]
            output.ts = tx[1]
                
            rc = lowlevel.sm_switch_channel_output(output)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_output',
                                        self.name)

            self.tdm.add(SpeechEndpoint(self, 'tx'), tx)

            rx = self.module.timeslots.allocate(self.ts_type)
            self.info.ist = rx[0]
            self.info.its = rx[1]

            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st = rx[0]
            input.ts = rx[1]

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input',
                                        self.name)
            
            self.tdm.add(SpeechEndpoint(self, 'rx'), rx)

        log.debug('%s tx: %d:%d, rx: %d:%d card: %d',
                  self.name, self.info.ost, self.info.ots,
                  self.info.ist, self.info.its, self.info.card)

    def get_module(self):
        """Return a unique identifier for module comparisons.
        Used by switching."""
        if TiNG_version[0] < 2:
            return (self.card, self.module)

        return self.module

    def get_switch(self):
        """Return a unique identifier for switch card comparisons.
        Used by switching."""
        if TiNG_version[0] < 2:
            return self.info.card

        return self.card.card_id
        
    def get_timeslot(self):
        """Get the tx timeslot for TDM switch connections."""
        
        if self.info.ost == -1:
            self.tdm_connect()

        return (self.info.ost, self.info.ots, self.ts_type)
            
    def get_datafeed(self):
        """Get the datafeed."""

        if TiNG_version[0] < 2:
            return None

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
        
        @param source: a tuple (stream, timeslot, [timeslot_type]) or a
        transmitter instance (VMPtx, FMPtx or TDMtx), which must be on
        the same module.

        Used internally. Applications should use L{switching.connect}."""

        if hasattr(source, 'get_datafeed') and source.get_datafeed():
            connect = lowlevel.SM_CHANNEL_DATAFEED_CONNECT_PARMS()
            connect.channel = self.channel
            connect.data_source = source.get_datafeed()

            rc = lowlevel.sm_channel_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_channel_datafeed_connect',
                                        self.name)

            log_switch.debug('%s := %s (datafeed)', self.name, source.name)

            return SpeechEndpoint(self, 'datafeed')

        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st = source[0]
            input.ts = source[1]

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input(%d:%d)' %
                                        (input.st, input.ts), self.name)

            log_switch.debug('%s := %d:%d (sm)', self.name,
                             source[0], source[1])

            return SpeechEndpoint(self, 'rx')
        
        if self.info.ist == -1:
            self.tdm_connect()

        output = lowlevel.OUTPUT_PARMS()

        output.ost = self.info.ist		# sink
        output.ots = self.info.its
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        rc = lowlevel.sw_set_output(self.get_switch(), output)
        if (rc):
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusEndpoint(self.get_switch(),
                             (self.info.ist, self.info.its))

    def speak_to(self, sink):
        """Speak to a timeslot.

        @param sink: a tuple (stream, timeslot).
        
        Used internally. Applications should use L{switching.connect}."""

        if self.info.card == -1:
            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st = sink[0]
            output.ts = sink[1]

            rc = lowlevel.sm_switch_channel_output(output)
            if rc:
                return AculabSpeechError(
                    rc, 'sm_switch_channel_output(%d:%d)' %
                    (output.st, output.ts), self.name)

            log_switch.debug('%s speak_to(%d:%d)', self.name,
                             sink[0], sink[1])

            return SpeechEndpoint(self, 'tx')

        if self.info.ost == -1:
            self.tdm_connect()
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost = sink[0]                # sink
        output.ots = sink[1] 
        output.mode = lowlevel.CONNECT_MODE
        output.ist = self.info.ost			# source
        output.its = self.info.ots

        rc = lowlevel.sw_set_output(self.get_switch(), output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusEndpoint(self.card.card_id, sink)

    def listen_for(self, toneset = 0,
                   mode = lowlevel.kSMToneDetectionMinDuration40,
                   cptone_recognition = False, grunt_detection = False,
                   grunt_latency = 0, min_noise_level = 0.0,
                   grunt_threshold = 0.0):
                   
        """Start DTMF/Tone detection.

        @param toneset: toneset for DTMF/tone detection. The default toneset
        will recognize DTMF only. The string 'dtmf/fax' will use a combined
        DTMF/FAX toneset.

        @param mode: the algorithm to use for tone detection.
        See U{sm_listen_for
        <http://www.aculab.com/support/TiNG/gen/apifn-sm_listen_for.html>} for
        a list of available algorithms.
        """

        self.tone_set_id = toneset
        self.tone_detection_mode = mode

        if type(toneset) in (str, unicode):
            if toneset.lower() == 'dtmf/fax':
                # Incomplete: does not work for non-TiNG yet
                self.tone_set_id = self.module.dtmf_fax_toneset()
            else:
                raise ValueError('invalid toneset %s' % toneset)

        listen_for = lowlevel.SM_LISTEN_FOR_PARMS()
        listen_for.channel = self.channel
        listen_for.active_tone_set_id = self.tone_set_id
        listen_for.tone_detection_mode = mode
        if toneset <= 1:
            listen_for.map_tones_to_digits = lowlevel.kSMDTMFToneSetDigitMapping
        listen_for.enable_cptone_recognition = cptone_recognition
        listen_for.enable_grunt_detection = grunt_detection
        listen_for.grunt_latency = grunt_latency

        if TiNG_version[0] >= 2:
            listen_for.min_noise_level = min_noise_level
            listen_for.grunt_threshold = grunt_threshold
        
        rc = lowlevel.sm_listen_for(listen_for)
        if rc:
            raise AculabSpeechError(rc, 'sm_listen_for', self.name)

        log.debug('%s listening for DTMF/Tones with toneset %d', self.name,
                  self.tone_set_id)

        if self.event_recog is None:
            self.event_recog = self.set_event(lowlevel.kSMEventTypeRecog)
        
            # add the recog event to the reactor
            self.reactor.add(self.event_recog, self.on_recog)

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
    
    def play(self, file, volume = 0, agc = 0, speed = 0, filetype = None):
        """Play a file.

        This is a shorthand to create and start a L{PlayJob}."""

        job = PlayJob(self, file, agc, volume, speed, filetype)

        self.start(job)

    def record(self, file, max_octets = 0,
               max_elapsed_time = 0.0, max_silence = 0.0, elimination = 0,
               agc = 0, volume = 0, filetype = None):
        """Record to an alaw file.

        This is a shorthand to create and starts a L{RecordJob}."""

        job = RecordJob(self, file, max_octets,
                        max_elapsed_time, max_silence, elimination,
                        agc, volume)

        self.start(job)

    def tone(self, tone, duration = 0.0):
        """Send a predefined output tone."""

        job = ToneJob(self, tone, duration)

        self.start(job)

    def digits(self, digits, inter_digit_delay = 0, digit_duration = 0):
        """Send a string of DTMF digits."""

        job = DigitsJob(self, digits, inter_digit_delay,
                        digit_duration)

        self.start(job)

    def silence(self, duration = 0.0):
        """Play silence.

        This is a shorthand to create and start a L{SilenceJob}."""

        job = SilenceJob(self, duration)

        self.start(job)

    def faxrx(self, file, subscriber_id = '', transport = (None, None)):
        """Receive a FAX asynchronously.

        @param file: The name of a TIFF file that will receive the image.
        @param subscriber_id: The alphanumerical id of the station.
        @param vmp: A pair of (vmptx, vmprx) if this FAX is to be received
        on a RTP connection."""

        job = FaxRxJob(self, file, subscriber_id, transport)

        self.start(job)        

    def faxtx(self, file, subscriber_id = '', transport = (None, None)):
        """Transmit a FAX asynchronously.

        @param file: The name of a TIFF file that contains the image to send.
        @param subscriber_id: The alphanumerical id of the station.
        @param vmp: A pair of (vmptx, vmprx) if this FAX is to be received
        on a RTP connection."""

        job = FaxTxJob(self, file, subscriber_id, transport)

        self.start(job)        

    def on_recog(self):
        # log.debug('%s on_recog', self.name)
        recog = lowlevel.SM_RECOGNISED_PARMS()
        tone = None
        
        while True:
            recog.channel = self.channel

            rc = lowlevel.sm_get_recognised(recog)
            if rc:
                raise AculabSpeechError(rc, 'sm_get_recognised', self.name)

            if recog.type == lowlevel.kSMRecognisedNothing:
                return
            elif recog.type == lowlevel.kSMRecognisedDigit:
                tone = chr(recog.param0)
                log.debug('%s recognised %s: %s', self.name,
                          tonetype[recog.type], tone)
            elif recog.type == lowlevel.kSMRecognisedTone:
                tone = self.module.translate_tone(self.tone_set_id,
                                                  self.tone_detection_mode,
                                                  recog)[0]
                
                log.debug('%s recognised %s: %s (%d:%d)', self.name,
                          tonetype[recog.type], tone, recog.param0,
                          recog.param1)
            else:
                log.debug('%s recognised %s: %d:%d', self.name,
                          tonetype[recog.type], recog.param0, recog.param1)

            if tone:
                self.lock()
                try:
                    self.controller.dtmf(self, tone, self.user_data)        
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
            self.unlock()
            self._close()
        else:
            self.unlock()

        f = getattr(self.controller, fn, None)
        if f:
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

class Glue(object):
    """Glue logic to tie a SpeechChannel to a Call.

    This class is meant to be a base-class for the data of a single call
    with a Prosody channel for speech processing.

    It will allocate a I{SpeechChannel} upon creation and connect it to the
    call.
    When deleted, it will close and disconnect the I{SpeechChannel}."""
    
    def __init__(self, controller, module, call, auto_connect = True):
        """Allocate a speech channel on module and connect it to the call.

        @param controller: The controller will be passed to the SpeechChannel
        @param module: The module to open the SpeechChannel on. May be either
            a C{tSMModuleId} or an offset.
        @param call: The call that the SpeechChannel will be connected to.
        @param auto_connect: Set to False if call and speech channel should
        not be connected automatically.
        """
        
        self.call = call
        # initialize to None in case an exception is raised
        self.speech = None
        self.connection = None
        call.user_data = self
        self.speech = SpeechChannel(controller, module, user_data = self)
        if auto_connect:
            self.connection = connect(call, self.speech)

    def __del__(self):
        self.close()

    def close(self):
        """Disconnect and close the SpeechChannel.

        If you do not call this method, you may end up with a memory leak
        of uncollectable cyclic references."""
        if self.connection:
            self.connection.close()
            self.connection = None
            
        if self.speech:
            self.speech.close()
            self.speech = None

        self.call = None

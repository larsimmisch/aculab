import sys
import os
import time
import threading
import logging
import lowlevel
import names
from busses import Connection, CTBusConnection, DefaultBus
from error import *

if os.name == 'nt':
    import pywintypes
    import win32api
    import win32event
else:
    import select

__all__ = ['SpeechDispatcher', 'PlayJob', 'RecordJob', 'DigitsJob',
           'SpeechConnection', 'SpeechChannel', 'version']

log = logging.getLogger('speech')
log_switch = logging.getLogger('switch')

# check driver info and create prosody streams if TiNG detected
driver_info = lowlevel.SM_DRIVER_INFO_PARMS()
lowlevel.sm_get_driver_info(driver_info)
version = (driver_info.major, driver_info.minor)

def swig_value(s):
    a = s.find('_')
    if a != -1:
        o = s.find('_', a+1)
        return s[a+1:o]

    return s            

class Glue:
    '''Create a SpeechChannel and glue it to a call.'''
    
    def __init__(self, controller, module, call):
        self.call = call
        # initialize to None in case an exception is raised
        self.speech = None
        self.connection = None
        call.user_data = self
        self.speech = SpeechChannel(controller, module, user_data = self)
        self.connection = call.connect(self.speech)

    def __del__(self):
        self.close()

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.speech:
            self.speech.close()
            self.speech = None
            
# this class is only needed on Windows
class Win32DispatcherThread(threading.Thread):
    """Helper class for Win32SpeechEventDispatcher.
    
    WaitForMultipleObjects is limited to 64 objects,
    so multiple dispatcher threads are needed."""

    def __init__(self, mutex, handle = None, method = None):
        self.queue = []
        self.wakeup = win32event.CreateEvent(None, 0, 0, None)
        self.mutex = mutex
        # handles is a map from handles to method
        if handle:
            self.handles = { self.wakeup: None, handle: method }
        else:
            self.handles = { self.wakeup: None }
        
        threading.Thread.__init__(self)

    def update(self):
        self.mutex.acquire()
        try:
            while self.queue:
                add, handle, method = self.queue.pop(0)
                if add:
                    # print 'added 0x%04x' % handle
                    self.handles[handle] = method
                else:
                    # print 'removed 0x%04x' % handle
                    del self.handles[handle]

        finally:
            self.mutex.release()

        return self.handles.keys()

    def run(self):
        handles = self.handles.keys()

        while handles:
            try:
                rc = win32event.WaitForMultipleObjects(handles, 0, -1)
            except win32event.error, e:
                # 'invalid handle' may occur if an event is deleted
                # before the update arrives
                if e[0] == 6:
                    handles = self.update()
                    continue
                else:
                    raise
                
            if rc == win32event.WAIT_OBJECT_0:
                handles = self.update()
            else:
                self.mutex.acquire()
                try:
                    m = self.handles[handles[rc - win32event.WAIT_OBJECT_0]]
                finally:
                    self.mutex.release()

                try:
                    if m:
                        m()
                except StopIteration:
                    return
                except KeyboardInterrupt:
                    raise
                except:
                    log.error('error in Win32DispatcherThread main loop',
                          exc_info=1)
        
class Win32SpeechEventDispatcher:
    """Prosody Event dispatcher for Windows."""

    def __init__(self):
        self.mutex = threading.Lock()
        self.dispatchers = []
        self.running = False
        
    def add(self, handle, method):
        self.mutex.acquire()
        try:
            for d in self.dispatchers:
                if len(d.handles) < win32event.MAXIMUM_WAIT_OBJECTS:
                    d.queue.append((1, handle, method))
                    win32event.SetEvent(d.wakeup)
                    
                    return

            # if no dispatcher has a spare slot, create a new one
            d = Win32DispatcherThread(self.mutex, handle, method)
            if self.running:
                d.setDaemon(1)
                d.start()
            self.dispatchers.append(d)
        finally:
            self.mutex.release()

    def remove(self, handle):
        self.mutex.acquire()
        try:
            for d in self.dispatchers:
                if d.handles.has_key(handle):
                    d.queue.append((0, handle, None))
                    win32event.SetEvent(d.wakeup)
        finally:
            self.mutex.release()

    def start(self):
        if not self.dispatchers:
            self.dispatchers.append(Win32DispatcherThread(self.mutex))

        self.running = True
        
        for d in self.dispatchers:
            d.setDaemon(1)
            d.start()

    def run(self):
        if not self.dispatchers:
            self.dispatchers.append(Win32DispatcherThread(self.mutex))

        self.running = True

        for d in self.dispatchers[1:]:
            d.setDaemon(1)
            d.start()
        self.dispatchers[0].run()
        
class PollSpeechEventDispatcher(threading.Thread):
    """Prosody Event dispatcher for Unix systems with poll(), most notably
    Linux."""

    def __init__(self):
        threading.Thread.__init__(self)
        self.handles = {}
        self.mutex = threading.Lock()
        self.queue = []

        # create a pipe to add/remove fds
        pfds = os.pipe()
        self.pipe = (os.fdopen(pfds[0], 'rb', 0), os.fdopen(pfds[1], 'wb', 0))
        self.setDaemon(1)
        self.poll = select.poll()

        # listen to the read fd of our pipe
        self.poll.register(self.pipe[0], select.POLLIN)
        
    def add(self, handle, method):
        "blocks until handle is added by dispatcher thread"
        h = handle.fileno()
        if threading.currentThread() == self or not self.isAlive():
            # print 'self adding', h
            self.handles[h] = method
            self.poll.register(h)
        else:
            # print 'adding', h
            event = threading.Event()
            self.mutex.acquire()
            self.handles[h] = method
            # function 1 is add
            self.queue.append((1, h, event))
            self.mutex.release()
            self.pipe[1].write('1')
            event.wait()

    def remove(self, handle):
        "blocks until handle is removed by dispatcher thread"
        h = handle.fileno()
        if threading.currentThread() == self or not self.isAlive():
            # print 'self removing', h
            del self.handles[h]
            self.poll.unregister(h)
        else:
            # print 'removing', h
            event = threading.Event()
            self.mutex.acquire()
            del self.handles[h]
            # function 0 is remove
            self.queue.append((0, h, event))
            self.mutex.release()
            self.pipe[1].write('0')        
            event.wait()

    def run(self):
        
        while True:
            try:
                active = self.poll.poll()
                for a, mode in active:
                    if a == self.pipe[0].fileno():
                        self.pipe[0].read(1)
                        self.mutex.acquire()
                        try:
                            add, fd, event = self.queue.pop(0)
                        finally:
                            self.mutex.release()
                        if add:
                            self.poll.register(fd)
                        else:
                            self.poll.unregister(fd)

                        if event:
                            event.set()
                    else:
                        self.mutex.acquire()
                        try:
                            m = self.handles.get(a, None)
                        finally:
                            self.mutex.release()

                        # ignore method not found
                        if m:
                            m()
            except StopIteration:
                return
            except KeyboardInterrupt:
                raise
            except:
                log.error('error in PollSpeechEventDispatcher main loop',
                          exc_info=1)

if os.name == 'nt':
    SpeechDispatcher = Win32SpeechEventDispatcher()
else:
    SpeechDispatcher = PollSpeechEventDispatcher()

class PlayJob:

    def __init__(self, channel, f, agc = 0,
                 speed = 0, volume = 0, job_data = None):
        self.channel = channel
        self.job_data = job_data
        self.position = 0
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
        self.buffer = lowlevel.SM_TS_DATA_PARMS()
        self.length = self.file.tell()
        self.file.seek(0, 0)
        
    def start(self):
        'Do not call this method directly - call SpeechChannel.start instead'
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
            raise AculabSpeechError(rc, 'sm_replay_start')

        log.debug('%s play(%s, agc=%d, speed=%d, volume=%d)',
                  self.channel.name, str(self.file), self.agc,
                  self.speed, self.volume)
                  
        # add the write event to the dispatcher
        self.channel.dispatcher.add(self.channel.event_write,
                                    self.fill_play_buffer)

        self.fill_play_buffer()

        return self

    def done(self):
        # remove the write event from the dispatcher
        self.channel.dispatcher.remove(self.channel.event_write)

        # Position is only nonzero when play was stopped.
        channel = self.channel
        # break cyclic reference
        self.channel = None
        
        # Compute reason.
        reason = None
        if self.position:
            reason = AculabStopped()
            pos = self.position
        else:
            pos = self.length

        f = self.file

        if hasattr(self, 'filename'):
            self.file.close()
            self.file = None
            f = self.filename

        # no locks held - maybe too cautious
        log.debug('%s play_done(reason=\'%s\', pos=%d)',
                  channel.name, reason, pos)

        # channel.user_data, self.job_data)
        channel.job_done(self, 'play_done', f, reason, pos)

    def fill_play_buffer(self):
        status = lowlevel.SM_REPLAY_STATUS_PARMS()

        while True:
            status.channel = self.channel.channel

            rc = lowlevel.sm_replay_status(status)
            if rc:
                raise AculabSpeechError(rc, 'sm_replay_status')

            if status.status == lowlevel.kSMReplayStatusNoCapacity:
                return
            elif status.status == lowlevel.kSMReplayStatusComplete:
                self.done()
                return
            elif status.status != lowlevel.kSMReplayStatusCompleteData:
                data = self.buffer
                data.channel = self.channel.channel
                data.setdata(self.file.read(
                    lowlevel.kSMMaxReplayDataBufferSize))

                rc = lowlevel.sm_put_replay_data(data)
                if rc and rc != lowlevel.ERR_SM_NO_CAPACITY:
                    raise AculabSpeechError(rc, 'sm_put_replay_data')

    def stop(self):
        stop = lowlevel.SM_REPLAY_ABORT_PARMS()
        stop.channel = self.channel.channel
        rc = lowlevel.sm_replay_abort(stop)
        if rc:
            raise AculabSpeechError(rc, 'sm_replay_abort')
        
        self.position = stop.offset

        log.debug('%s play_stop()', self.channel.name)

class RecordJob:
    
    def __init__(self, channel, f, max_octets = 0,
                 max_elapsed_time = 0, max_silence = 0, elimination = 0,
                 agc = 0, volume = 0, job_data = None):

        self.channel = channel
        # f may be a string - if it is, close self.file in done
        if type(f) == type(''):
            self.file = file(f, 'wb')
            self.filename = f
        else:
            self.file = f

        self.buffer = lowlevel.SM_TS_DATA_PARMS()
        self.buffer.allocrecordbuffer()
        # size in bytes
        self.size = 0
        self.max_octets = max_octets
        self.max_elapsed_time = max_elapsed_time
        self.max_silence = max_silence
        self.elimination = elimination
        self.agc = agc
        self.volume = volume
        self.job_data = job_data
        self.reason = None

    def start(self):
        'Do not call this method directly - call SpeechChannel.start instead'
        
        record = lowlevel.SM_RECORD_PARMS()
        record.channel = self.channel.channel
        record.type = lowlevel.kSMDataFormatALawPCM
        record.sampling_rate = 8000
        record.max_octets = self.max_octets
        record.max_elapsed_time = self.max_elapsed_time
        record.max_silence = self.max_silence
        record.elimination = self.elimination
        record.agc = self.agc
        record.volume = self.volume

        rc = lowlevel.sm_record_start(record)
        if rc:
            raise AculabSpeechError(rc, 'sm_record_start')

        log.debug('%s record(%s, max_octets=%d, max_time=%d, max_silence=%d, '
                  'elimination=%d, agc=%d, volume=%d)',
                  self.channel.name, str(self.file), self.max_octets,
                  self.max_elapsed_time, self.max_silence, self.elimination,
                  self.agc, self.volume)
                  
        # add the read event to the dispatcher
        self.channel.dispatcher.add(self.channel.event_read, self.on_read)

    def __del__(self):
        self.buffer.freerecordbuffer()

    def done(self):                
        # remove the read event from the dispatcher
        self.channel.dispatcher.remove(self.channel.event_read)

        channel = self.channel
        # break cyclic reference
        self.channel = None

        f = self.file
        if hasattr(self, 'filename'):
            self.file.close()
            self.file = None
            f = self.filename
        
        # no locks held - maybe too cautious
        log.debug('%s record_done(reason=\'%s\', size=%d)',
                  channel.name, self.reason, self.size)

        channel.job_done(self, 'record_done', f, self.reason, self.size)
    
    def on_read(self):
        status = lowlevel.SM_RECORD_STATUS_PARMS()

        while True:
            status.channel = self.channel.channel

            rc = lowlevel.sm_record_status(status)
            if rc:
                self.reason = AculabSpeechError(rc, 'sm_record_status')
                self.done()
                return

            if status.status == lowlevel.kSMRecordStatusComplete:
                if version[0] >= 2:
                    term = status.termination_reason
                    # Todo check
                    rc = status.param0
                else:
                    how = lowlevel.SM_RECORD_HOW_TERMINATED_PARMS()
                    how.channel = self.channel.channel

                    rc = lowlevel.sm_record_how_terminated(how)
                    if rc:
                        raise AculabSpeechError(rc, 'sm_record_how_terminated')

                    term = how.termination_reason
                    rc = -1
        
                self.reason = None
                if term == lowlevel.kSMRecordHowTerminatedLength:
                    self.reason = AculabTimeout()
                elif term == lowlevel.kSMRecordHowTerminatedMaxTime:
                    self.reason = AculabTimeout()
                elif term == lowlevel.kSMRecordHowTerminatedSilence:
                    self.reason = AculabSilence()
                elif term == lowlevel.kSMRecordHowTerminatedAborted:
                    self.reason = AculabStopped()
                elif term == lowlevel.kSMRecordHowTerminatedError:
                    self.reason = AculabSpeechError(rc, 'RecordJob')
                    
                self.done()
                return
            elif status.status == lowlevel.kSMRecordStatusNoData:
                return
            else:
                data = self.buffer
                data.channel = self.channel.channel
                data.length = lowlevel.kSMMaxRecordDataBufferSize

                rc = lowlevel.sm_get_recorded_data(data)
                if rc:
                    try:
                        self.stop()
                    finally:
                        self.reason = AculabSpeechError(rc,
                                                        'sm_get_recorded_data')
                    self.done()

                d = data.getdata()
                self.size += len(d)

                self.file.write(d)

    def stop(self):
        abort = lowlevel.SM_RECORD_ABORT_PARMS()
        abort.channel = self.channel.channel
        rc = lowlevel.sm_record_abort(abort)
        if rc:
            raise AculabSpeechError(rc, 'sm_record_abort')

        log.debug('%s record_stop()', self.channel.name)

class DigitsJob:
    
    def __init__(self, channel, digits, inter_digit_delay = 32,
                 digit_duration = 64, job_data = None):
        self.channel = channel
        self.digits = digits
        self.inter_digit_delay = inter_digit_delay
        self.digit_duration = digit_duration
        self.job_data = job_data
        self.stopped = False

    def start(self):
        'Do not call this method directly - call SpeechChannel.start instead'
        
        dp = lowlevel.SM_PLAY_DIGITS_PARMS()
        dp.channel = self.channel.channel
        dp.digits.type = lowlevel.kSMDTMFDigits
        dp.digits.digit_string = self.digits
        dp.digits.inter_digit_delay = self.inter_digit_delay
        dp.digits.digit_duration = self.digit_duration

        rc = lowlevel.sm_play_digits(dp)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_digits')

        log.debug('%s digits(%s, inter_digit_delay=%d, digit_duration=%d)',
                  self.channel.name, self.digits, self.inter_digit_delay,
                  self.digit_duration)

        # add the write event to the dispatcher
        self.channel.dispatcher.add(self.channel.event_write, self.on_write)

    def on_write(self):
        if self.channel is None:
            return
        
        status = lowlevel.SM_PLAY_DIGITS_STATUS_PARMS()
        status.channel = self.channel.channel

        rc = lowlevel.sm_play_digits_status(status)
        if rc:
            raise AculabSpeechError(rc, 'sm_play_digits_status')

        if status.status == lowlevel.kSMPlayDigitsStatusComplete:

            channel = self.channel
            # break cyclic reference
            self.channel = None
            
            reason = None
            if self.stopped:
                reason = AculabStopped()

            # remove the write event from to the dispatcher
            channel.dispatcher.remove(channel.event_write)

            log.debug('%s digits_done(reason=\'%s\')',
                      channel.name, reason)

            channel.job_done(self, 'digits_done', reason)
                
    def stop(self):
        self.stopped = True
        log.debug('%s disgits_stop()', self.channel.name)

        # remove the write event from the dispatcher
        self.channel.dispatcher.remove(self.channel.event_write)

        # Position is only nonzero when play was stopped.
        channel = self.channel
        # break cyclic reference
        self.channel = None
        
        # Compute reason.
        reason = None
        if self.position:
            reason = AculabStopped()
            pos = self.position
        else:
            pos = self.length

        f = self.file

        if hasattr(self, 'filename'):
            self.file.close()
            self.file = None
            f = self.filename

        # no locks held - maybe too cautious
        log.debug('%s play_done(reason=\'%s\', pos=%d)',
                  channel.name, reason, pos)

        # channel.user_data, self.job_data)
        channel.job_done(self, 'play_done', f, reason, pos)

class DCReadJob:
    
    def __init__(self, channel, cmd, min_to_collect, min_idle = 0,
                 blocking = 0, job_data = None):

        '''Arguments are mostly from dc_rx_control'''
        self.channel = channel
        self.cmd = cmd
        self.min_to_collect = min_to_collect
        self.min_idle = min_idle
        self.blocking = blocking
        self.job_data = job_data

    def start(self):
        'Do not call this method directly - call SpeechChannel.start instead'

        control = lowlevel.SMDC_RX_CONTROL_PARMS()

        control.channel = self.channel.channel
        control.cmd = self.cmd
        control.min_to_collect = self.min_to_collect
        control.min_idle = self.min_idle
        control.blocking = self.blocking

        # add the read event to the dispatcher
        self.channel.dispatcher.add(self.channel.event_read, self.on_read)

        rc = lowlevel.smdc_rx_control(control)
        if rc:
            raise AculabSpeechError(rc, 'smdc_rx_control')

        log.debug('%s dc_rx_control(cmd=%d, min_to_collect=%d, ' \
                  'min_idle=%d, blocking=%d)',
                  self.channel.name, self.cmd, self.min_to_collect,
                  self.min_idle, self.blocking)

    def on_read(self):
        self.channel.controller.dc_read(self.channel)

    def stop(self):
        rc = lowlevel.smdc_stop(self.channel.channel)
        if rc:
            raise AculabSpeechError(rc, 'smdc_stop')

        # remove the write event from the dispatcher
        self.channel.dispatcher.remove(self.channel.event_read)

        # Position is only nonzero when play was stopped.
        channel = self.channel
        # break cyclic reference
        self.channel = None
        
        # no locks held - maybe too cautious
        log.debug('%s dc_read stopped',
                  channel.name)

        # channel.user_data, self.job_data)
        channel.job_done(self, 'dc_read_done', f, reason, pos)

class SpeechConnection:    
    def __init__(self, channel, direction):
        self.channel = channel
        self.direction = direction
        if direction not in ['in', 'out']:
            raise ValueError('direction must be \'in\' or \'out\'')

    def close(self):
        if self.channel:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel.channel
            input.st = -1
            input.ts = -1

            if self.direction == 'in':
                rc = lowlevel.sm_switch_channel_input(input)
                if rc:
                    raise AculabSpeechError(rc, 'sm_switch_channel_input')
            else:
                rc = lowlevel.sm_switch_channel_output(input)
                if rc:
                    raise AculabSpeechError(rc, 'sm_switch_channel_output')

            log_switch.debug('%s disconnected(%s)', self.channel.name,
                             self.direction)

            self.channel = None

    def __del__(self):
        self.close()

class SpeechChannel:
    """A full duplex Prosody channel with events"""
        
    def __init__(self, controller, card = 0, module = 0, mutex = None,
                 user_data = None, dispatcher = SpeechDispatcher):
        """Allocate a full duplex Prosody channel and add the events to
        dispatcher.

        Controllers must implement:
        - play_done(channel, file, reason, position,
                    user_data, job_data)
        - dtmf(channel, digit, user_data)
        - record_done(channel, file, reason, size, user_data, job_data)
        - digits_done(channel, reason, user_data, job_data).
        
        Reason is an exception or None (for normal termination).

        The module parameter is either the Prosody Sharc DSP number or
        a snapshot.Module instance.
        
        If a mutex is passed in, it will be acquired before any controller
        method is invoked and released as soon as it returns"""

        self.card = card
        self.controller = controller
        self.dispatcher = dispatcher
        self.mutex = mutex
        self.user_data = user_data
        self.job = None
        self.close_pending = None
        # initialize early before any exception is thrown
        self.event_read = None
        self.event_write = None
        self.event_recog = None
        self.in_ts = None
        self.out_ts = None
        self.channel = None
        self.name = None

        if version[0] >= 2:
            import snapshot
            s = snapshot.Snapshot()

            if type(module) == type(0):
                module = s.prosody[card].modules[module].open.module_id

        self.module = module

        alloc = lowlevel.SM_CHANNEL_ALLOC_PLACED_PARMS()
        alloc.type = lowlevel.kSMChannelTypeFullDuplex
        alloc.module = self.module
        
        rc = lowlevel.sm_channel_alloc_placed(alloc)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_alloc_placed')

        self.channel = alloc.channel

        self.name = '0x%04x' % self.channel

        self.info = lowlevel.SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = lowlevel.sm_channel_info(self.info)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_info')

        # initialise our events
        self.event_read = self.set_event(lowlevel.kSMEventTypeReadData)
        self.event_write = self.set_event(lowlevel.kSMEventTypeWriteData);
        self.event_recog = self.set_event(lowlevel.kSMEventTypeRecog)

        # add the recog event to the dispatcher
        self.dispatcher.add(self.event_recog, self.on_recog)

        if version[0] >= 2:
            self._ting_connect()
            log.debug('%s out: %d:%d, in: %d:%d', self.name, self.info.ost,
                      self.info.ots, self.info.ist, self.info.its)
        self._listen()

    def __del__(self):
        self._close()
        if self.name:
            log.debug('%s deleted', self.name)

    def _close(self):
        self.lock()
        try:
            if self.event_read:
                lowlevel.smd_ev_free(self.event_read)
                self.event_read = None
            if self.event_write:
                lowlevel.smd_ev_free(self.event_write)
                self.event_write = None
            if self.event_recog:
                lowlevel.smd_ev_free(self.event_recog)
                self.dispatcher.remove(self.event_recog)
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
                    raise AculabSpeechError(rc, 'sm_channel_release')
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

        # switch to local timeslots for TiNG
        if self.info.ost == -1:
            self.out_ts = self.module.timeslots.allocate()
            self.info.ost, self.info.ots = self.out_ts

            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st, output.ts = self.out_ts
                
            rc = lowlevel.sm_switch_channel_output(output)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_output')

            self.out_connection = SpeechConnection(self, 'out')

        if self.info.ist == -1:
            self.in_ts = self.module.timeslots.allocate()
            self.info.ist, self.info.its = self.in_ts

            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st, input.ts = self.in_ts

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input')
            
            self.in_connection = SpeechConnection(self, 'in')


    def _listen(self):
        listen_for = lowlevel.SM_LISTEN_FOR_PARMS()
        listen_for.channel = self.channel
        listen_for.tone_detection_mode = \
                                  lowlevel.kSMToneLenDetectionMinDuration40;
        listen_for.map_tones_to_digits = lowlevel.kSMDTMFToneSetDigitMapping;
        rc = lowlevel.sm_listen_for(listen_for)
        if rc:
            raise AculabSpeechError(rc, 'sm_listen_for')

    def close(self):
        self.lock()
        self.close_pending = 1
        self.unlock()
        if self.job:
            self.job.stop()
            return

        self._close()
        
    def lock(self):
        if self.mutex:
            self.mutex.acquire()

    def unlock(self):
        if self.mutex:
            self.mutex.release()

    def create_event(self, event):
        """event has type SM_CHANNEL_SET_EVENT_PARMS and is modified in place
        The handle is returned"""
        
        if os.name == 'nt':
            rc, event.event = lowlevel.smd_ev_create(event.channel,
                                                     event.event_type,
                                                     event.issue_events)
            if rc:
                raise AculabSpeechError(rc, 'smd_ev_create')

            return pywintypes.HANDLE(event.event)

        rc = lowlevel.smd_ev_create(event.event,
                                    event.channel,
                                    event.event_type,
                                    event.issue_events)
        if rc:
            raise AculabSpeechError(rc, 'smd_ev_create')

        return event.event.copy()

    def set_event(self, type):
        event = lowlevel.SM_CHANNEL_SET_EVENT_PARMS()

        event.channel = self.channel
        event.issue_events = lowlevel.kSMChannelSpecificEvent
        event.event_type = type
        handle = self.create_event(event)

        rc = lowlevel.sm_channel_set_event(event)
        if rc:
            lowlevel.smd_ev_free(event.handle)
            raise AculabSpeechError(rc, 'sm_channel_set_event')

        return handle

    def listen_to(self, source):
        """Listen to a timeslot.
        Source is a tuple (stream, timeslot)"""
        
        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st, input.ts = source

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input(%d:%d)' %
                                        (input.st, input.ts))

            log_switch.debug('%s listen_to(%d:%d)', self.name,
                             source[0], source[1])

            return SpeechConnection(self, 'in')
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost = self.info.ist		# sink
        output.ots = self.info.its
        output.mode = lowlevel.CONNECT_MODE
        output.ist, output.its = source

        # this is ridiculous: Aculab should decide whether
        # they want to work with offsets or card_ids
        card = Snapshot().switch[self.info.card].card.card_id            
        rc = lowlevel.sw_set_output(card, output)
        if (rc):
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusConnection(card, (self.info.ist, self.info.its))

    def speak_to(self, sink):
        """Speak to a timeslot. Sink is a tuple (stream, timeslot)"""

        if self.info.card == -1:
            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st, output.ts = sink

            rc = lowlevel.sm_switch_channel_output(output)
            if rc:
                return AculabSpeechError(rc,
                                         'sm_switch_channel_output(%d:%d)' %
                                         (output.st, output.ts))

            log_switch.debug('%s speak_to(%d:%d)', self.name,
                             sink[0], sink[1])

            return SpeechConnection(self, 'out')
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost, output.ots = sink       # sink
        output.mode = lowlevel.CONNECT_MODE
        output.ist = self.info.ost			# source
        output.its = self.info.ots

        # this is ridiculous: Aculab should decide whether
        # they want to work with offsets or card_ids
        card = Snapshot().switch[self.info.card].card.card_id
        rc = lowlevel.sw_set_output(card, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        log_switch.debug('%s %d:%d := %d:%d', self.name,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusConnection(card, sink)

    def connect(self, other, bus = DefaultBus):
        """Connect to another SpeechChannel or a CallHandle.

        Keep the returned reference until the connection should be broken."""
        if isinstance(other, SpeechChannel):
            c = Connection(bus)
            if self.info.card == other.info.card:
                if other == self:
                    c.timeslots = [ bus.allocate() ]
                    c.connections = [self.speak_to(c.timeslots[0]),
                                     self.listen_to(c.timeslots[0])]
                else:
                    # connect directly
                    c.connections = [self.listen_to((other.info.ost,
                                                     other.info.ots)),
                                     other.listen_to((self.info.ost,
                                                      self.info.ots))]
            else:
                # allocate two timeslots
                c.timeslots = [ bus.allocate(), bus.allocate() ]
                # make connections
                c.connections = [ other.speak_to(c.timeslots[0]),
                                  self.listen_to(c.timeslots[0]),
                                  self.speak_to(c.timeslots[1]),
                                  other.listen_to(c.timeslots[1]) ]

            return c
        
        else:
            # assume other is a CallHandle subclass and delegate to it
            return other.connect(self)

    def dc_config(self, protocol, pconf, encoding, econf):
        'Configure the channel for data communications'
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
            raise AculabSpeechError(rc, 'smdc_channel_config')

    def start(self, job):
        if self.job:
            raise RuntimeError('Already executing job')

        if not self.close_pending:
            self.job = job
            job.start()
    
    def play(self, file, volume = 0, agc = 0, speed = 0, job_data = None):
        """Play an alaw file asynchronously. The token job_data is passed
        back in play_done.
        The file parameter may be a file object or a string.
        If it is a string, a file with that name is automatically openend and
        closed. File objects are played and not rewound or closed at the end"""

        job = PlayJob(self, file, agc, volume, speed, job_data)

        self.start(job)

    def record(self, file, max_octets = 0,
               max_elapsed_time = 0, max_silence = 0, elimination = 0,
               agc = 0, volume = 0, job_data = None):
        """Record an alaw file asynchronously. The token job_data is passed
        back in record_done.
        The file parameter may be a file object or a string.
        If it is a string, a file with that name is automatically openend and
        closed. File objects are recorded to and not rewound or closed at
        the end"""


        job = RecordJob(self, file, max_octets,
                        max_elapsed_time, max_silence, elimination,
                        agc, volume, job_data)

        self.start(job)

    def digits(self, digits, inter_digit_delay = 32, digit_duration = 64,
               job_data = None):
        """Send a string of DTMF digits asynchronously. The token job_data
        is passed back in digits_done."""

        job = DigitsJob(self, digits, inter_digit_delay,
                        digit_duration, job_data)

        self.start(job)

    def faxrx(self, file, subscriber_id = '', job_data = None):
        """Receive a FAX asynchronously. The token job_data
        is passed back in faxrx_done."""

        job = FaxRxJob(self, file, subscriber_id, job_data)

        self.start(job)        

    def faxtx(self, file, subscriber_id = '', job_data = None):
        """Transmit a FAX asynchronously. The token job_data
        is passed back in faxtx_done."""

        job = FaxTxJob(self, file, subscriber_id, job_data)

        self.start(job)        

    def on_recog(self):
        recog = lowlevel.SM_RECOGNISED_PARMS()
        
        while True:
            recog.channel = self.channel

            rc = lowlevel.sm_get_recognised(recog)
            if rc:
                raise AculabSpeechError(rc, 'sm_get_recognised')

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
        args += (self.user_data, job.job_data)

        self.lock()
        self.job = None
        if self.close_pending:
            self.close()
        self.unlock()

        f = getattr(self.controller, fn)
        f(self, reason, *args, **kwargs)
        m = getattr(self.controller, 'job_done', None)
        if m:
            m(job)

class Conference:
    def __init__(self, module = None, mutex = None):
        self.module = module
        self.listeners = 0
        self.speakers = 0
        self.mutex = mutex

    def lock(self):
        if self.mutex:
            self.mutex.acquire()

    def unlock(self):
        if self.mutex:
            self.mutex.release()

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


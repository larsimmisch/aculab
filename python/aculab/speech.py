import sys
import lowlevel
from busses import CTBusConnection, ProsodyLocalBus, DefaultBus
from error import AculabError, AculabSpeechError
import threading
import os
import time
if os.name == 'nt':
    import pywintypes
    import win32api
    import win32event
else:
    import marshal
    import select

__all__ = ['SpeechEventDispatcher', 'PlayJob', 'RecordJob',
           'DigitsJob', 'SpeechConnection', 'SpeechChannel', 'version']

# check driver info and create prosody streams if TiNG detected
driver_info = lowlevel.SM_DRIVER_INFO_PARMS()
lowlevel.sm_get_driver_info(driver_info)
version = (driver_info.major, driver_info.minor)

if version[0] >= 2:
    prosodystreams = []

    cards = lowlevel.sm_get_cards()
    for i in range(cards):
        card_info = lowlevel.SM_CARD_INFO_PARMS()
        card_info.card = i
        lowlevel.sm_get_card_info(card_info)
        for j in range(card_info.module_count):
            prosodystreams.append(ProsodyLocalBus(j))

# this class is only needed on Windows
class Win32DispatcherThread(threading.Thread):
    
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

                m()
        

class Win32SpeechEventDispatcher:
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
    def __init__(self):
        threading.Thread.__init__(self)
        self.handles = {}
        self.mutex = threading.Lock()

        # create a pipe to add/remove fds
        pfds = os.pipe()
        self.pipe = (os.fdopen(pfds[0], 'rb'), os.fdopen(pfds[1], 'wb'))
        self.setDaemon(1)
        
    def add(self, handle, method):
        h = handle.fileno()
        # function 1 is add
        self.mutex.acquire()
        self.handles[h] =  method
        self.mutex.release()
        marshal.dump((1, h), self.pipe[1])
        # we must flush, otherwise the reading end will block
        self.pipe[1].flush()

    def remove(self, handle):
        h = handle.fileno()
        self.mutex.acquire()
        del self.handles[h]
        self.mutex.release()
        # function 0 is remove
        marshal.dump((0, h), self.pipe[1])
        # we must flush, otherwise the reading end will block
        self.pipe[1].flush()

    def run(self):
        p = select.poll()

        # listen to the read fd of our pipe
        p.register(self.pipe[0], select.POLLIN)

        while 1:
            active = p.poll()
            for a, mode in active:
                if a == self.pipe[0].fileno():
                    add, fd = marshal.load(self.pipe[0])
                    if add:
                        p.register(fd)
                    else:
                        p.unregister(fd)
                else:
                    self.mutex.acquire()
                    try:
                        m = self.handles.get(a, None)
                    finally:
                        self.mutex.release()

                    # ignore method not found
                    if m:
                        m()

if os.name == 'nt':
    SpeechEventDispatcher = Win32SpeechEventDispatcher
else:
    SpeechEventDispatcher = PollSpeechEventDispatcher

class PlayJob:
    def __init__(self, filename, user_data):
        self.filename = filename
        self.user_data = user_data
        # open the file and read the length
        self.file = open(filename, 'rb')
        self.file.seek(0, 2)
        self.buffer = lowlevel.SM_TS_DATA_PARMS()
        self.length = self.file.tell()
        self.file.seek(0, 0)
        self.position = 0        

class RecordJob:
    def __init__(self, filename, user_data):
        self.filename = filename
        self.user_data = user_data
        self.file = open(filename, 'wb')
        self.buffer = lowlevel.SM_TS_DATA_PARMS()
        self.buffer.allocrecordbuffer()
        # size in bytes
        self.size = 0

    def __del__(self):
        self.buffer.freerecordbuffer()
        

class DigitsJob:
    def __init__(self, user_data):
        self.user_data = user_data

class SpeechConnection:    
    def __init__(self, channel):
        self.channel = channel

    def close(self):
        # print "disabling", self.channel
        input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

        input.channel = self.channel
        input.st = -1
        input.ts = -1

        rc = lowlevel.sm_switch_channel_input(input)
        if (rc):
            raise AculabSpeechError(rc, 'sm_switch_channel_input')

    def __del__(self):
        self.close()

class SpeechChannel:
        
    def __init__(self, controller, dispatcher, module = -1):
        """Controllers must implement play_done(channel, position, user_data),
        dtmf(channel, digit), record_done(channel, how, size, user_data) and
        digits_done(channel, user_data)
        If they have a mutex attribute, the mutex will be acquired
        before any method is invoked and release as soon as it returns"""

        self.controller = controller
        self.dispatcher = dispatcher
        self.playjob = None
        self.digitsjob = None
        self.recordjob = None
        self.signaljob = None

        if module != -1:
            self.module = module
            alloc = lowlevel.SM_CHANNEL_ALLOC_PLACED_PARMS();

            alloc.type = lowlevel.kSMChannelTypeFullDuplex;
            alloc.module = module;

            rc = lowlevel.sm_channel_alloc_placed(alloc);
            if rc:
                raise AculabSpeechError(rc, 'sm_channel_alloc_placed');
        else:
            alloc = lowlevel.SM_CHANNEL_ALLOC_PARMS();

            alloc.type = lowlevel.kSMChannelTypeFullDuplex;

            rc = lowlevel.sm_channel_alloc(alloc);
            if rc:
                raise AculabSpeechError(rc, 'sm_channel_alloc');            

        self.channel = alloc.channel

        self.info = lowlevel.SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = lowlevel.sm_channel_info(self.info)
        if rc:
            raise AculabSpeechError(rc, 'sm_channel_info')

        # workaround for bug in TiNG
        global version
        if version[0] >= 2:
            self.info.card = 0

        # initialise our events
        self.event_read = self.set_event(lowlevel.kSMEventTypeReadData)
        self.event_write = self.set_event(lowlevel.kSMEventTypeWriteData);
        self.event_recog = self.set_event(lowlevel.kSMEventTypeRecog)

        # add the recog event to the dispatcher
        self.dispatcher.add(self.event_recog, self.on_recog)

        if version[0] >= 2:
            # switch to local timeslots for TiNG
            if self.info.ost == -1:
                self.out_ts = prosodystreams[module].allocate()
                self.info.ost, self.info.ots = self.out_ts

                output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

                output.channel = self.channel
                output.st, output.ts = self.out_ts

                rc = lowlevel.sm_switch_channel_output(output)
                if (rc):
                    raise AculabSpeechError(rc, 'sm_switch_channel_output')

                self.out_connection = SpeechConnection(self.channel)


            if self.info.ist == -1:
                self.in_ts = prosodystreams[module].allocate()
                self.info.ist, self.info.its = self.in_ts

                input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

                input.channel = self.channel
                input.st, input.ts = self.in_ts

                rc = lowlevel.sm_switch_channel_input(input)
                if (rc):
                    raise AculabSpeechError(rc, 'sm_switch_channel_input')

                self.in_connection = SpeechConnection(self.channel)

        # don't do sm_listen_for for TiNG
        # Todo: why not?
        if version[0] < 2:
            listen_for = lowlevel.SM_LISTEN_FOR_PARMS()
            listen_for.channel = self.channel
            listen_for.tone_detection_mode = \
                                    lowlevel.kSMToneLenDetectionMinDuration40;
            listen_for.map_tones_to_digits = \
                                           lowlevel.kSMDTMFToneSetDigitMapping;
            rc = lowlevel.sm_listen_for(listen_for)
            if rc:
                raise AculabSpeechError(rc, 'sm_listen_for')

    def __del__(self):
        self.release()

    def __cmp__(self, other):
        return self.channel.__cmp__(other.channel)

    def __hash__(self):
        return self.channel

    def release(self):
        if hasattr(self, 'event_read') and self.event_read:
            lowlevel.smd_ev_free(self.event_read)
            self.event_read = None
        if hasattr(self, 'event_recog') and self.event_recog:
            # Remove the recog event from the dispatcher.
            self.dispatcher.remove(self.event_recog)

            # Deleting the event may trigger
            # an 'invalid handle' error in the dispatcher due to a race
            # condition.
            # This error is caught, however.
            lowlevel.smd_ev_free(self.event_recog)
            self.event_recog = None
        if hasattr(self, 'event_write') and self.event_write:
            lowlevel.smd_ev_free(self.event_write)

        global prosodystreams
        if hasattr(self, 'out_ts') and self.out_ts:
            # attribute out_ts implies attribute module
            prosodystreams[self.module].free(out_ts)
            self.out_ts = None

        if hasattr(self, 'in_ts') and self.in_ts:
            # attribute in_ts implies attribute module
            prosodystreams[self.module].free(in_ts)
            self.in_ts = None

        if self.channel:
            rc = lowlevel.sm_channel_release(self.channel)
            if rc:
                raise AculabSpeechError(rc, 'sm_channel_release')

            self.channel = None

    def create_event(self, event):
        """event has type SM_CHANNEL_SET_EVENT_PARMS and is modified in place
        The handle is returned"""
        
        if os.name == 'nt':
            rc, event.handle = lowlevel.smd_ev_create(event.channel,
                                                      event.event_type,
                                                      event.issue_events)
            if rc:
                raise AculabSpeechError(rc, 'smd_ev_create')

            return pywintypes.HANDLE(event.handle)
        else:
            event.handle = lowlevel.tSMEventId()
            rc = lowlevel.smd_ev_create(event.handle,
                                        event.channel,
                                        event.event_type,
                                        event.issue_events)

            if rc:
                raise AculabSpeechError(rc, 'smd_ev_create')
            
            return event.handle

    def set_event(self, type):
        event = lowlevel.SM_CHANNEL_SET_EVENT_PARMS()

        event.channel = self.channel
        event.issue_events = lowlevel.kSMChannelSpecificEvent
        event.event_type = type
        
        handle = self.create_event(event)
        
        rc = lowlevel.sm_channel_set_event(event)
        if rc:
            lowlevel.smd_ev_free(handle)
            raise AculabSpeechError(rc, 'sm_channel_set_event')

        return handle

    def listen_to(self, source):
        """source is a tuple (stream, timeslot"""
        
        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st, input.ts = source

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabSpeechError(rc, 'sm_switch_channel_input(%d:%d)' %
                                        (input.st, input.ts))

            return SpeechConnection(self.channel)
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost = self.info.ist		# sink
        output.ots = self.info.its
        output.mode = lowlevel.CONNECT_MODE
        output.ist, output.its = source
            
        rc = lowlevel.sw_set_output(self.info.card, output)
        if (rc):
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        return CTBusConnection(self.info.card, (self.info.ist, self.info.its))

    def speak_to(self, sink):
        """sink is a tuple (stream, timeslot"""

        if self.info.card == -1:
            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st, output.ts = sink

            rc = lowlevel.sm_switch_channel_output(output)
            if rc:
                return AculabSpeechError(rc,
                                         'sm_switch_channel_output(%d:%d)' %
                                         (output.st, output.ts))

            return SpeechConnection(self.channel)
        
        output = lowlevel.OUTPUT_PARMS()

        output.ost, output.ots = sink       # sink
        output.mode = lowlevel.CONNECT_MODE
        output.ist = self.info.ost			# source
        output.its = self.info.ots

        rc = lowlevel.sw_set_output(self.info.card, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d, %d:%d := %d:%d)' %
                              (self.info.card, output.ost, output.ots,
                               output.ist, output.its))

        return CTBusConnection(self.info.card, sink)

    def connect(self, other, bus = DefaultBus):
        if isinstance(other, SpeechChannel):
            c = Connection(bus)
            if self.info.card == other.info.card:
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
    
    def play(self, filename, volume = 0, agc = 0, speed = 0, user_data = None):
        """only plays alaw (asynchronously)
        user_data is passed back in play_done"""

        self.playjob = PlayJob(filename, user_data)

        replay = lowlevel.SM_REPLAY_PARMS()
        replay.channel = self.channel
        replay.agc = agc
        replay.speed = speed
        replay.volume = volume
        replay.type = lowlevel.kSMDataFormat8KHzALawPCM
        replay.data_length = self.playjob.length

        rc = lowlevel.sm_replay_start(replay)
        if rc:
            self.playjob = None
            raise AculabSpeechError(rc, 'sm_replay_start')

        # add the write event to the dispatcher
        self.dispatcher.add(self.event_write, self.on_write)

        self.fill_play_buffer()

    def fill_play_buffer(self):
        status = lowlevel.SM_REPLAY_STATUS_PARMS()

        while True:
            status.channel = self.channel

            rc = lowlevel.sm_replay_status(status)
            if rc:
                raise AculabSpeechError(rc, 'sm_replay_status')

            if status.status == lowlevel.kSMReplayStatusNoCapacity:
                return
            elif status.status == lowlevel.kSMReplayStatusComplete:

                # remove the write event from the dispatcher
                self.dispatcher.remove(self.event_write)
                
                if hasattr(self.controller, 'mutex'):
                    self.controller.mutex.acquire()

                # position is only nonzero when play was stopped,
                if self.playjob.position:
                    pos = self.playjob.position
                else:
                    pos = self.playjob.length

                try:
                    self.controller.play_done(self, pos, self.playjob.user_data)
                finally:
                    self.playjob = None

                    # release mutex
                    if hasattr(self.controller, 'mutex'):
                        self.controller.mutex.release()
                        
                return
            
            elif status.status != lowlevel.kSMReplayStatusCompleteData:
                data = self.playjob.buffer
                data.channel = self.channel
                data.setdata(self.playjob.file.read(
                    lowlevel.kSMMaxReplayDataBufferSize))

                rc = lowlevel.sm_put_replay_data(data)
                if rc:
                    raise AculabSpeechError(rc, 'sm_put_replay_data')

    def digits(self, digits, inter_digit_delay = 32, digit_duration = 64,
               user_data = None):

        self.digitsjob = DigitsJob(user_data)

        dp = lowlevel.SM_PLAY_DIGITS_PARMS()
        dp.channel = self.channel
        dp.digits.type = lowlevel.kSMDTMFDigits
        dp.digits.digit_string = digits
        dp.digits.inter_digit_delay = inter_digit_delay
        dp.digits.digit_duration = digit_duration

        rc = lowlevel.sm_play_digits(dp)
        if rc:
            self.digitsjob = None
            raise AculabSpeechError(rc, 'sm_play_digits')

        # add the write event to the dispatcher
        self.dispatcher.add(self.event_write, self.on_write)

    def on_write(self):
        if self.playjob:
            self.fill_play_buffer()
        elif self.digitsjob:
            status = lowlevel.SM_PLAY_DIGITS_STATUS_PARMS()
            status.channel = self.channel

            rc = lowlevel.sm_play_digits_status(status)
            if rc:
                raise AculabSpeechError(rc, 'sm_play_digits_status')

            if status.status == lowlevel.kSMPlayDigitsStatusComplete:
                
                # remove the write event from to the dispatcher
                self.dispatcher.remove(self.event_write)

                if hasattr(self.controller, 'mutex'):
                    self.controller.mutex.acquire()

                try:
                    self.controller.digits_done(self, self.digitsjob.user_data)
                finally:
                    self.digitsjob = None

                # release mutex
                if hasattr(self.controller, 'mutex'):
                    self.controller.mutex.release()

    def stop_play(self):
        if self.playjob:
            stop = lowlevel.SM_REPLAY_ABORT_PARMS()
            stop.channel = self.channel
            rc = lowlevel.sm_replay_abort(stop)
            if rc:
                raise AculabSpeechError(rc, 'sm_replay_abort')
        
            self.playjob.position = stop.offset

    def record(self, filename, max_octets = 0, max_elapsed_time = 0,
               max_silence = 0, elimination = 0, agc = 0, volume = 0,
               user_data = None):
        
        self.recordjob = RecordJob(filename, user_data)

        record = lowlevel.SM_RECORD_PARMS()
        record.channel = self.channel
        record.type = lowlevel.kSMDataFormat8KHzALawPCM
        record.max_octets = max_octets
        record.max_elapsed_time = max_elapsed_time
        record.max_silence = max_silence
        record.elimination = 0
        record.agc = agc
        record.volume = 0

        rc = lowlevel.sm_record_start(record)
        if rc:
            self.recordjob = None
            raise AculabSpeechError(rc, 'sm_record_start')

        # add the read event to the dispatcher
        self.dispatcher.add(self.event_read, self.on_read)

    def on_read(self):
        status = lowlevel.SM_RECORD_STATUS_PARMS()

        while self.recordjob:
            status.channel = self.channel

            rc = lowlevel.sm_record_status(status)
            if rc:
                raise AculabSpeechError(rc, 'sm_record_status')

            if status.status == lowlevel.kSMRecordStatusComplete:
                
                if not self.recordjob:
                    return

                # remove the read event from the dispatcher
                self.dispatcher.add(self.event_read, self.on_read)

                how = lowlevel.SM_RECORD_HOW_TERMINATED_PARMS()
                how.channel = self.channel

                rc = lowlevel.sm_record_how_terminated(how)
                if rc:
                    raise AculabSpeechError(rc, 'sm_record_how_terminated')

                if hasattr(self.controller, 'mutex'):
                    self.controller.mutex.acquire()

                try:
                    self.controller.record_done(self, how.termination_reason,
                                                self.recordjob.size,
                                                self.recordjob.user_data)
                finally:
                    self.recordjob = None

                    # release mutex
                    if hasattr(self.controller, 'mutex'):
                        self.controller.mutex.release()
                        
                return
            
            elif status.status == lowlevel.kSMRecordStatusNoData:
                return
            else:
                data = self.recordjob.buffer
                data.channel = self.channel
                data.length = lowlevel.kSMMaxRecordDataBufferSize

                rc = lowlevel.sm_get_recorded_data(data)
                if rc:
                    raise AculabSpeechError(rc, 'sm_get_recorded_data')

                d = data.getdata()
                self.recordjob.size += len(d)

                self.recordjob.file.write(d)

    def stop_record(self):
        if self.recordjob:
            abort = lowlevel.SM_RECORD_ABORT_PARMS()
            abort.channel = self.channel
            rc = lowlevel.sm_record_abort(abort)
            if rc:
                raise AculabSpeechError(rc, 'sm_record_abort')

    def on_recog(self):
        recog = lowlevel.SM_RECOGNISED_PARMS()
        
        while 1:
            recog.channel = self.channel

            rc = lowlevel.sm_get_recognised(recog)
            if rc:
                raise AculabSpeechError(rc, 'sm_get_recognised')

            if recog.type == lowlevel.kSMRecognisedNothing:
                return
            elif recog.type == lowlevel.kSMRecognisedDigit:
                
                if hasattr(self.controller, 'mutex'):
                    self.controller.mutex.acquire()

                try:
                    self.controller.dtmf(self, chr(recog.param0))
                finally:
                    if hasattr(self.controller, 'mutex'):
                        self.controller.mutex.release()
            
    def stop(self):
        self.stop_play()
        self.stop_record()
    

# Copyright (C) 2002-2007 Lars Immisch

"""Various reactors for Windows and Unix and utilities for portable event
handling.

The portable event handling is a bit more convoluted than I'd like, but the
situation is complicated:

On Windows, C{tSMEventId} is a typedef to C{HANDLE}. On Unix, it is a
structure with an C{fd} and a C{mode} member.

On Unix, we need the mode when adding the event, so it would be logical to
always pass C{tSMEventId} instances around and deal with the differences
in the reactor implementations.

But that doesn't work, because the VMPrx etc. manage their own events, and
(presumably) delete them as soon as they are stopped, so for this part of
the code - on Unix - it is only safe to keep a reference to the file
descriptor.

The following strategy is currently used:

We have L{add_event} and L{remove_event} methods in this module.

L{add_event} returns a handle that can be passed directly to reactor.remove.
The VMPrx etc. store this value and call reactor.remove() directly.

L{remove_event} takes a C{tSMEventId} as event parameter. This is used
by the L{SpeechChannel} that is required to manage its own events explicitly.
"""

import threading
import select
import os
import logging
# local imports
import lowlevel
from util import curry, create_pipe
from names import event_name
from error import AculabError


log = logging.getLogger('reactor')
log_call = logging.getLogger('call')
log_speech = logging.getLogger('speech')

# These events are not set in call.last_event because they don't
# change the state of the call as far as we are concerned
# They are delivered to the controller, of course
no_state_change_events = [lowlevel.EV_CALL_CHARGE,
                          lowlevel.EV_CHARGE_INT,
                          lowlevel.EV_DETAILS]

no_state_change_extended_events = [lowlevel.EV_EXT_FACILITY,
                                   lowlevel.EV_EXT_UUI_PENDING,
                                   lowlevel.EV_EXT_UUI_CONGESTED,
                                   lowlevel.EV_EXT_UUI_UNCONGESTED,
                                   lowlevel.EV_EXT_UUS_SERVICE_REQUEST,
                                   lowlevel.EV_EXT_TRANSFER_INFORMATION]


if os.name == 'nt':
    import pywintypes
    import win32api
    import win32event

    def add_event(reactor, event, method):
        """Add an event to a reactor.

        @param reactor: The reactor to add the event to
        @param event: A C{tSMEventId} structure.
        @return: a OS dependent value that can be used for reactor.remove()
        """
        reactor.add(event, method)
        return event

    def remove_event(reactor, event):
        """Remove an event for a reactor.

        @param event: A C{tSMEventId} structure.
        """
        reactor.remove(event)

else:
    def add_event(reactor, event, method):
        """Add an event to a reactor.

        @param reactor: The reactor to add the event to
        @param event: A C{tSMEventId} structure
        @return: a OS dependent value that can ve used for reactor.remove()
        """        
        reactor.add(event.fd, event.mode, method)
        return event.fd

    def remove_event(reactor, event):
        """Remove an event for a reactor.

        @param event: A C{tSMEventId} structure.
        """
        reactor.remove(event.fd)

class CallEventThread(threading.Thread):
    """This is a helper thread for call events on v5 drivers.

    On v5, we cannot use the standard reactor for call events, but we'd
    like to have all callbacks coming from the same thread, because this
    requires no locking.
    
    We use this thread to get events for all call handles and send
    them to the dispatcher through a pipe.
    """

    def __init__(self):
        self.calls = {}
        self.pipes = {}
        self.mutex = threading.Lock()
        threading.Thread.__init__(self)

    def add(self, reactor, call):
        self.mutex.acquire()
        try:
            self.calls[call.handle] = (call, reactor)
            # If the pipe doesn't exist, create and install it
            pipe = self.pipes.get(call, None)
            if pipe is None:
                pipe = create_pipe()
                self.pipes[reactor] = pipe
                reactor.add(pipe[0].fileno(), select.POLLIN, 
                            curry(self.on_event, pipe[0]))

        finally:
            self.mutex.release()

    def remove(self, reactor, call):
        # Todo: clean up pipes to the reactor
        self.mutex.acquire()
        try:
            del self.calls[call.handle]
        finally:
            self.mutex.release()

    def on_event(self, pipe):
        event = lowlevel.STATE_XPARMS()

        event.read(pipe)
        
        # log_call.debug('got event %s for 0x%x on %s',
        #                event_name(event), event.handle, pipe)
        
        self.mutex.acquire()
        call, reactor = self.calls.get(event.handle, (None, None))
        if not call:
            self.mutex.release()
            log_call.error('got event %s for nonexisting call 0x%x',
                           event_name(event), event.handle)    
            return
        
        self.mutex.release()
        call_dispatch(call, event)

    def process(self, event):
        self.mutex.acquire()
        call, reactor = self.calls.get(event.handle, (None, None))
        if not call:
            self.mutex.release()
            log_call.error('got event %s for nonexisting call 0x%x',
                           event_name(event), event.handle)
            
            return
        
        # Get the pipe to the reactor
        pipe = self.pipes.get(reactor, None)
        self.mutex.release()

        # log_call.debug('sending %s', event_name(event))
        # Write the event to the pipe
        event.write(pipe[1])

    def run(self):
        event = lowlevel.STATE_XPARMS()
        
        while True:
            event.handle = 0
            event.timeout = 200

            rc = lowlevel.call_event(event)
            if rc:
                raise AculabError(rc, 'call_event')

            # process the event
            if event.handle:
                self.process(event)

_call_event_thread = None

# Unused
def dispatch(controller, method, *args, **kwargs):
    m = getattr(controller, method, None)
    if not m:
        log.warn('%s not implemented on %s', method, controller)
        return

    try:
        m(*args, **kwargs)
    except:
        log.error('error in %s', method, exc_info=1)

def call_dispatch(call, event):

    ev = event_name(event).lower()

    mutex = getattr(call.user_data, 'mutex', None)
    if mutex:
        mutex.acquire()

    handlers = [] # list of tuples (handle, name, args)
    handled = 'ignored'

    try:
        h = getattr(call, ev, None)
        if h:
            handlers.append((h, 'call', None))
        h = getattr(call.controllers[-1], ev, None)
        if h:
            handlers.append((h, 'controller',
                             (call, call.user_data)))
        h = getattr(call, ev + '_post', None)
        if h:
            handlers.append((h, 'post', None))

        # compute description of handlers
        if handlers:
            l = [h[1] for h in handlers]
            handled = ','.join(l)

        log_call.debug('%s %s (%s)', call.name, ev, handled)

        for h, n, args in handlers:
            if args:
                h(*args)
            else:
                h()

    finally:
        # set call.last_event and call.last_extended_event
        if event.state == lowlevel.EV_EXTENDED \
           and event.extended_state \
           not in no_state_change_extended_events:
            call.last_event = lowlevel.EV_EXTENDED
            call.last_extended_event = event.extended_state
        elif event.state not in no_state_change_events:
            call.last_event = event.state
            call.last_extended_event = None

        if mutex:
            mutex.release()

def call_on_event(call):
    event = lowlevel.STATE_XPARMS()
    
    event.handle = call.handle
    rc = lowlevel.call_event(event)
    if rc:
        raise AculabError(rc, 'call_event')

    call_dispatch(call, event)
    
def add_call_event(reactor, call):
    """Add a call event to the reactor."""
    
    if lowlevel.cc_version < 6:
        global _call_event_thread
        if not _call_event_thread:
            log_call.debug("starting V5 call event helper thread")
            _call_event_thread = CallEventThread()
            _call_event_thread.setDaemon(1)
            _call_event_thread.start()

            _call_event_thread.add(reactor, call)

            return call.handle
    else:
        chwo = lowlevel.CALL_HANDLE_WAIT_OBJECT_PARMS()
        chwo.handle = call.handle

        rc = lowlevel.call_get_handle_event_wait_object(chwo)
        if rc:
            raise AculabError(rc, 'call_get_handle_event_wait_object')

        # This is a bit nasty - we set an attribute on call
        call.event = chwo.wait_object.fileno()

        # Note the curry
        reactor.add(call.event, chwo.wait_object.mode(),
                    curry(call_on_event, call))

        return call.event

def remove_call_event(reactor, call):
    if lowlevel.cc_version < 6:
        global _call_event_thread
        if _call_event_thread:
            _call_event_thread.remove(call)
    else:
        reactor.remove(call.event)
        call.event = None

if os.name == 'nt':

    # this class is only needed on Windows
    class Win32ReactorThread(threading.Thread):
        """Helper thread for Win32Reactor.

        WaitForMultipleObjects is limited to 64 objects,
        so multiple reactor threads are needed."""

        def __init__(self, mutex, handle = None, method = None):
            """Create a Win32DispatcherThread."""
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
            """Used internally.

            Update the internal list of objects to wait for."""
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
            """The Win32ReactorThread run loop. Should not be called
            directly."""

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
                        log.error('error in Win32ReactorThread main loop',
                              exc_info=1)

    class Win32Reactor(object):
        """Prosody Event reactor for Windows.

        Manages multiple reactor threads if more than 64 event handles are used.
        Each SpeechChannel uses 3 event handles, so this happens quickly."""

        def __init__(self):
            self.mutex = threading.Lock()
            self.reactors = []
            self.running = False

        def add(self, event, method):
            """Add a new handle to the reactor.

            @param event: The event to watch.
            @param method: This will be called when the event is fired."""
            handle = pywintypes.HANDLE(event)
            self.mutex.acquire()
            try:
                for d in self.reactors:
                    if len(d.handles) < win32event.MAXIMUM_WAIT_OBJECTS:
                        d.queue.append((1, handle, method))
                        win32event.SetEvent(d.wakeup)

                        return

                # if no reactor has a spare slot, create a new one
                d = Win32ReactorThread(self.mutex, handle, method)
                if self.running:
                    d.setDaemon(1)
                    d.start()
                self.reactors.append(d)
            finally:
                self.mutex.release()

        def remove(self, event):
            """Remove an event from the reactor.

            @param handle: The handle of the Event to watch."""

            handle = pywintypes.HANDLE(event)
            self.mutex.acquire()
            try:
                for d in self.reactors:
                    if d.handles.has_key(handle):
                        d.queue.append((0, handle, None))
                        win32event.SetEvent(d.wakeup)
            finally:
                self.mutex.release()

        def start(self):
            """Start the reactor in a separate thread."""

            if not self.reactors:
                self.reactors.append(Win32ReactorThread(self.mutex))

            self.running = True

            for d in self.reactors:
                d.setDaemon(1)
                d.start()

        def run(self):
            """Run the reactor in the current thread."""

            if not self.reactors:
                self.reactors.append(Win32ReactorThread(self.mutex))

            self.running = True

            for d in self.reactors[1:]:
                d.setDaemon(1)
                d.start()
            self.reactors[0].run()

    Reactor = Win32Reactor()

else: # os.name == 'nt'
    
    maskmap = { select.POLLIN: 'POLLIN',
                select.POLLPRI: 'POLLPRI',
                select.POLLOUT: 'POLLOUT',
                select.POLLERR: 'POLLERR',
                select.POLLHUP: 'POLLHUP',
                select.POLLNVAL: 'POLLNVAL' }
           
    def maskstr(mask):
        "Print a eventmask for poll"

        l = []
        for v, s in maskmap.iteritems():
            if mask & v:
                l.append(s)

        return '|'.join(l)

    class PollReactor(threading.Thread):
        """Prosody Event reactor for Unix systems with poll(), most notably
        Linux.

        Experimental support for notifications."""

        def __init__(self):
            """Create a reactor."""
            threading.Thread.__init__(self)
            self.handles = {}
            self.mutex = threading.Lock()
            self.queue = []
            
            # create a pipe to add/remove fds
            self.pipe = create_pipe()
            self.setDaemon(1)
            self.poll = select.poll()

            # listen to the read fd of our pipe
            self.poll.register(self.pipe[0], select.POLLIN)

        def add(self, handle, mode, method):
            """Add an event to the reactor.

            @param handle: A file descriptor, B{not} a File object.
            @param mode: A bitmask of select.POLLOUT, select.POLLIN, etc.
            @param method: This will be called when the event is fired."""

            if not callable(method):
                raise ValueError('method must be callable')

            if threading.currentThread() == self or not self.isAlive():
                # log.debug('self adding fd: %d %s', handle, method.__name__)
                self.handles[handle] = method
                self.poll.register(handle, mode)
            else:
                # log.debug('adding fd: %d %s', handle, method.__name__)
                self.mutex.acquire()
                self.handles[handle] = method
                # function 1 is add
                self.queue.append((1, handle, mode))
                self.mutex.release()
                self.pipe[1].write('1')

        def remove(self, handle):
            """Remove a handle from the reactor.

            @param handle: A file descriptor.

            This method blocks until handle is removed by the reactor thread.
            """

            if threading.currentThread() == self or not self.isAlive():
                # log.debug('self removing fd: %d', handle)
                del self.handles[handle]
                self.poll.unregister(handle)
            else:
                # log.debug('removing fd: %d', handle)
                self.mutex.acquire()
                del self.handles[handle]
                # function 0 is remove
                self.queue.append((0, handle, None))
                self.mutex.release()
                self.pipe[1].write('0')

        def run(self):
            'Run the reactor.'
            while True:
                try:
                    active = self.poll.poll()
                    for a, mask in active:
                        if a == self.pipe[0].fileno():
                            self.pipe[0].read(1)
                            self.mutex.acquire()
                            try:
                                add, fd, mask = self.queue.pop(0)
                            finally:
                                self.mutex.release()
                            if add:
                                self.poll.register(fd, mask)
                            else:
                                self.poll.unregister(fd)

                        else:
                            self.mutex.acquire()
                            try:
                                m = self.handles.get(a, None)
                            finally:
                                self.mutex.release()

                            # log.info('event on fd %d %s: %s', a,
                            #         maskstr(mask), m.__name__)

                            # ignore missing method, it must have been removed
                            if m:
                                m()

                except StopIteration:
                    return
                except KeyboardInterrupt:
                    return
                except:
                    log.error('error in PollReactor main loop',
                              exc_info=1)
                    raise

    Reactor = PollReactor()

class PortEventDispatcher:
    def __init__(self, port, controller, user_data):
        self.port = port
        self.controller = controller
        self.user_data = user_data

    def __call__(self):
        n = lowlevel.CALL_PORT_NOTIFICATION_PARMS()
        n.port_id = port.get_port_id()
        
        rc = call_get_port_notification(n)
        if rc:
            raise AculabError(rc, 'call_get_port_notification')

        if n.event == lowlevel.ACU_CALL_EVT_L1_CHANGE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_L2_CHANGE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_HW_CLOCK_STOP:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_CONNECTIONLESS:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_FIRMWARE_CHANGE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_D_CHAN_SWITCHOVER:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_PORT_COMMS_LOST:
            pass
        elif n.event == lowlevel.ACU_IPT_EV_ADD_ALIAS_SUCCEEDED:
            pass
        elif n.event == lowlevel.ACU_IPT_EV_ADD_ALIAS_FAILED:
            pass
        elif n.event == lowlevel.ACU_IPT_EV_ALIAS_REMOVED:
            pass
        elif n.event == lowlevel.ACU_CALL_EV_INSUFFICIENT_MEDIA_RESOURCE:
            pass
        elif n.event == lowlevel.ACU_SIP_EV_RESPONSE:
            pass
        elif n.event == lowlevel.ACU_SIP_EV_REQUEST:
            pass
        elif n.event == lowlevel.ACU_SIP_EV_REQUEST_TIMEOUT:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_NO_CHANNEL_AVAILABLE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_BLOCKING_STATE_CHANGE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_RESET_STATE_CHANGE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_TRACE_MODE:
            pass
        elif n.event == lowlevel.ACU_CALL_EVT_TRACE_SNAPSHOT:
            pass
        

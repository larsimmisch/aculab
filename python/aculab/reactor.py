# Copyright (C) 2002-2008 Lars Immisch

"""Utilities for portable event handling.

The portable event handling is uglier than I'd like it, but the
situation is complicated:

On Windows, C{tSMEventId} is a typedef to C{HANDLE}. On Unix, it is a
structure with an C{fd} and a C{mode} member.

On Unix, we need the mode when adding the event, so it would seem ideal to
always pass C{tSMEventId} instances around and deal with the differences
in the reactor implementations.

But that doesn't work, because the VMPrx etc. manage their own events, and
(presumably) delete them as soon as they are stopped, so for this part of
the code - on Unix - we can't keep references to C[tSMEventId}s around -
it is only safe to keep a reference to the file descriptor.

The following strategy is currently used:

We have L{add_event} and L{remove_event} functions in this module.

L{add_event} returns a handle that can be passed directly to reactor.remove.
The VMPrx etc. store this value and call reactor.remove() directly.

L{remove_event} takes a C{tSMEventId} as event parameter. This is used
by the L{SpeechChannel} that manages its events explicitly.
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

if os.name == 'nt':
    import win32reactor
    import win32event

    add_event = win32reactor.add_event
    remove_event = win32reactor.remove_event

    Reactor = win32reactor.Win32Reactor()

else:
    import posixreactor

    add_event = posixreactor.add_event
    remove_event = posixreactor.remove_event

    Reactor = posixreactor.PollReactor()

class CallEventThread(threading.Thread):
    """This is a helper thread class for call events on v5 drivers.

    On v5, which is ancient, we cannot use the standard reactor for call
    events, but we want to have all callbacks coming from the same thread,
    because this requires no locking in the application and greatly simplifies
    the application design.
    
    We use this thread to get events for all call handles and send
    them to the actual reactor through a pipe and a queue.
    """

    # We have a chicken and egg problem when we create call handles
    # - we get the call handle after the openin/openout, but this thread
    # may receive events before the call knows its handle.
    # As a consequence, this thread has to queue events for any handle.
    
    # To avoid a silent memory leak, limit the queue size
    max_chicken_events = 4

    def __init__(self):
        self.calls = {}
        self.pipes = {}
        # map call handle to event queue
        self.events = {}
        self.mutex = threading.Lock()
        threading.Thread.__init__(self)

    def create_pipe(self, reactor):
        if os.name == 'nt':
            pipe = win32event.CreateEvent(None, 0, 0, None)
            self.pipes[reactor] = pipe
            reactor.add(pipe, curry(self.on_event, pipe))
        else:
            # Create a nonblocking pipe (if drained completely on reading,
            # this will behave like a Windows Event Semaphore)
            pipe = create_pipe(True)
            self.pipes[reactor] = pipe
            reactor.add(pipe[0].fileno(), select.POLLIN,
                        curry(self.on_event, pipe[0]))

    def add(self, reactor, call):
        self.mutex.acquire()
        try:
            self.calls[call.handle] = (call, reactor)
            # If the pipe doesn't exist, create and install it
            pipe = self.pipes.get(reactor, None)
            if pipe is None:
                self.create_pipe(reactor)
                
            # Pop the event queue
            events = self.events.get(call.handle, [])
            if events:
                del self.events[call.handle]
        finally:
            self.mutex.release()

        # log.debug('add: queue %s', events)

        # Dispatch events from the queue
        for e in events:
            call_dispatch(call, e)
            
    def remove(self, reactor, call):
        # Todo: clean up pipes to the reactor
        self.mutex.acquire()
        try:
            del self.calls[call.handle]
            if self.events.has_key(call.handle):
                del self.events[call.handle]
        finally:
            self.mutex.release()

    def on_event(self, pipe):
        if os.name != 'nt':
            # Drain the pipe
            while True:
                s = pipe.read(256)
                # log.debug('on_event pipe %s read: %d', pipe, len(s))
                if len(s) < 256:
                    break

        # Collect all events and translate call handle to call
        self.mutex.acquire()
        try:
            todo = [ (self.calls[handle][0], events)
                     for handle, events in self.events.iteritems() ]

            self.events = {}
        finally:
            self.mutex.release()

        # Dispatch all events
        for call, events in todo:
            for e in events:
                # log_call.debug('got event %s for 0x%x on %s',
                #                event_name(event), event.handle, pipe)
                call_dispatch(call, e)

    def enqueue(self, event):
        """Queue the event."""

        handle = event.handle
        
        self.mutex.acquire()
        try:
            # Queue the event
            if self.events.has_key(handle):
                events = self.events[handle]
                if len(events) > self.max_chicken_events:
                    raise RuntimeError("chicken queue overflow: 0x%x"
                                       % handle)
                events.append(event)
            else:
                self.events[handle] = [event]

            call, reactor = self.calls.get(handle, (None, None))
            # Get the pipe to the reactor
            pipe = self.pipes.get(reactor, None)
        finally:
            self.mutex.release()

        if pipe:
            # log_call.debug('%x sending %s', handle, event_name(event))
            # Write a notification to the pipe
            if os.name == 'nt':
                win32event.SetEvent(pipe)
            else:
                pipe[1].write('1')

    def run(self):
        """Thread main - Process call events."""

        while True:
            event = lowlevel.STATE_XPARMS()
            event.timeout = 200

            rc = lowlevel.call_event(event)
            if rc:
                raise AculabError(rc, 'call_event')

            # process the event
            if event.handle:
                self.enqueue(event)

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
    """Map a call event to the methods on the Call and Controller and call it.

    Methods on the Call object (if available) are called first, then methods
    on the controller.

    The Call object can have a special _post method for each event that is
    called last.
    """

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
            log.debug("starting V5 call event helper thread")
            _call_event_thread = CallEventThread()
            _call_event_thread.setDaemon(1)
            _call_event_thread.start()

        _call_event_thread.add(reactor, call)
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

def remove_call_event(reactor, call):
    if lowlevel.cc_version < 6:
        global _call_event_thread
        if _call_event_thread:
            _call_event_thread.remove(reactor, call)
    else:
        reactor.remove(call.event)
        call.event = None

class PortEventDispatcher:
    """Placeholder - not currently used."""

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
        

# Copyright (C) 2002-2008 Lars Immisch

"""Reactor implementation for Windows systems."""

import threading
import os
import logging
# local imports
import pywintypes
import win32api
import win32event

log = logging.getLogger('reactor')
log_call = logging.getLogger('call')

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

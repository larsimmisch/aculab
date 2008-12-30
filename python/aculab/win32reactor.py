# Copyright (C) 2002-2008 Lars Immisch

"""Reactor implementation for Windows systems."""

import threading
import os
import logging
import pywintypes
import win32api
import win32event
# local imports
from timer import TimerBase

log = logging.getLogger('reactor')

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

    def __init__(self, master, handle = None, method = None):
        """Create a Win32DispatcherThread."""
        self.queue = []
        self.wakeup = win32event.CreateEvent(None, 0, 0, None)
        self.master = master
        self.shutdown = False
        # handles is a map from handles to method
        if handle:
            self.handles = { self.wakeup: None, handle: method }
        else:
            self.handles = { self.wakeup: None }

        threading.Thread.__init__(self)

    def update(self):
        """Used internally.

        Update the internal list of objects to wait for."""
        self.master.mutex.acquire()
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
            self.master.mutex.release()

        return self.handles.keys()

    def stop(self):
        """Stop the thread."""
        self.shutdown = True
        win32event.SetEvent(self.wakeup)        

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
                if self.shutdown:
                    return
                
                handles = self.update()
            else:
                self.master.mutex.acquire()
                try:
                    m = self.handles[handles[rc - win32event.WAIT_OBJECT_0]]
                    self.master.enqueue(m)
                finally:
                    self.master.mutex.release()


class Win32Reactor(threading.Thread):
    """Event reactor for Windows.

    Manages multiple reactor threads to work around the 64 handles limitation.
    Each SpeechChannel uses 3 event handles, so this happens quickly.

    (This sucks, BTW, we need two context switches instead of one for each
    event. But we can't use IO Completion Ports here.

    An alternative would be to drop the guarantuee that all callbacks will
    be called from reactor.run, but that is not a friendly default)
    """

    def __init__(self):
        self.mutex = threading.Lock()
        self.reactors = []
        self.queue = []
        self.wakeup = win32event.CreateEvent(None, 0, 0, None)        
        self.timer = TimerBase()

        threading.Thread.__init__(self)

    def add_timer(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.'''

        self.mutex.acquire()
        try:
            t, adjust = self.timer.add(interval, function, args, kwargs)
        finally:
            self.mutex.release()

        # if the new timer is the next, wake up the timer thread to readjust
        # the wait period
        if adjust and threading.currentThread() != self and self.isAlive():
            win32event.SetEvent(self.wakeup)

        return t

    def cancel_timer(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError'''
        self.mutex.acquire()
        try:
            adjust = self.timer.cancel(timer)
        finally:
            self.mutex.release()
        
        if adjust and threading.currentThread() != self and self.isAlive():
            win32event.SetEvent(self.wakeup)

    def enqueue(self, m):
        """Internal for Win32ReactorThread:
        Queue a callback and signal the internal event.

        Only to be called with mutex locked.
        """

        self.queue.append(m)
        win32event.SetEvent(self.wakeup)

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
            d = Win32ReactorThread(self, handle, method)
            if self.isAlive():
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

    def start_workers(self):
        """Start the thread workers."""

        # Start at least one worker
        if not self.reactors:
            self.reactors.append(Win32ReactorThread(self))

        for d in self.reactors:
            d.setDaemon(1)
            d.start()

    def stop_workers(self):
        """Stop all worker threads."""

        self.mutex.acquire()
        try:
            for d in self.reactors:
                d.stop()
        finally:
            self.mutex.release()

        for d in self.reactors:
            d.join()

    def start(self):
        """Start the reactor in a new thread."""

        self.start_workers()
        threading.Thread.start(self)

    def run(self):
        """Run the reactor in the current thread."""
        
        self.mutex.acquire()
        try:
            self.start_workers()
            wait = self.timer.time_to_wait()
        finally:
            self.mutex.release()

        while True:

            # KeyboardInterrupt will not wake WaitForSingleObject, so we can't
            # sleep forever
            if wait < 0 or wait > 500:
                wait = 500

            try:
                win32event.WaitForSingleObject(self.wakeup, wait)
            except KeyboardInterrupt:
                self.stop_workers()
                raise

            self.mutex.acquire()
            try:
                todo = self.queue
                self.queue = []
                timers = self.timer.get_pending()
                wait = self.timer.time_to_wait()
            finally:
                self.mutex.release()

            try:
                for m in todo:
                    m()
                for t in timers:
                    t()

            except StopIteration:
                self.stop_workers()
                return
            except KeyboardInterrupt:
                self.stop_workers()
                raise
            except:
                log.error('error in Win32Reactor main loop', exc_info=1)
            

        

# Copyright (C) 2002-2009 Lars Immisch

"""Reactor implementation for Windows systems."""

from __future__ import with_statement 

import threading
import os
import logging
import win32api
import win32event
import time
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
        threading.Thread.__init__(self)
        self.queue = []
        self.wakeup = win32event.CreateEvent(None, 0, 0, None)
        self.master = master
        self.shutdown = False
        # handles is a map from integer handles to method
        if handle:
            self.handles = { self.wakeup: None, handle: method }
        else:
            self.handles = { self.wakeup: None }

    def update(self):
        """Used internally.

        Update the internal list of objects to wait for."""

        with self.master.mutex:
            while self.queue:
                add, handle, method = self.queue.pop(0)
                if add:
                    # log.debug('added %s: %s', handle, method)
                    self.handles[handle] = method
                else:
                    # log.debug('removed %s', handle)
                    del self.handles[handle]
                    # We must detach from the handle. If we don't, it will be
                    # closed twice, with undefined results.
                    handle.Detach()

            return self.handles.keys()

    def stop(self):
        """Stop the thread."""
        self.shutdown = True
        win32event.SetEvent(self.wakeup)        

    def run(self):
        """The Win32ReactorThread run loop. Should not be called
        directly."""

        handles = self.update()
        errors = 0
        
        while handles:
            try:
                # log.debug('handles: %s', handles)
                rc = win32event.WaitForMultipleObjects(handles, 0, -1)
                errors = 0
                
                h = handles[rc - win32event.WAIT_OBJECT_0]
                if h == self.wakeup:
                    if self.shutdown:
                        return

                    # log.debug('update')
                    handles = self.update()
                else:
                    with self.master.mutex:
                        m = self.handles[h]
                        self.master.enqueue(m)
                        
            except win32event.error, e:
                # 'invalid handle' occurs when an event is deleted
                if e[0] == 6:
                    # log.debug('update after invalid handle')
                    handles = self.update()
                    errors = errors +1
                    if errors > 2:
                        log.error('handles: %s', handles)
                        log.error('Error in Win32ReactorThread run loop',
                                  exc_info=1)
                        return
                    continue
                else:
                    log.error('Error in Win32ReactorThread run loop',
                              exc_info=1)
                    return
            except:
                log.error('Error in Win32ReactorThread run loop', exc_info=1)
                return


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
        threading.Thread.__init__(self)
        self.mutex = threading.Lock()
        self.reactors = []
        self.queue = []
        self.wakeup = win32event.CreateEvent(None, 0, 0, None)
        self.timer = TimerBase()

    def add_timer(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.'''

        with self.mutex:
            t, adjust = self.timer.add(interval, function, args, kwargs)

        # if the new timer is the next, wake up the timer thread to readjust
        # the wait period
        if adjust and threading.currentThread() != self and self.isAlive():
            win32event.SetEvent(self.wakeup)

        return t

    def cancel_timer(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError'''
        with self.mutex:
            adjust = self.timer.cancel(timer)
        
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

        # log.debug('adding: %s', event)
        with self.mutex:
            for d in self.reactors:
                if len(d.handles) < win32event.MAXIMUM_WAIT_OBJECTS:
                    d.queue.append((1, event, method))
                    # log.debug('wakeup')
                    win32event.SetEvent(d.wakeup)

                    return

            # if no reactor has a spare slot, create a new one
            # log.debug('added/created %d', event)
            d = Win32ReactorThread(self, event, method)
            self.reactors.append(d)
            if self.isAlive():
                d.start()
                
    def remove(self, event):
        """Remove an event from the reactor.

        @param handle: The handle of the Event to watch."""

        with self.mutex:
            for d in self.reactors:
                if d.handles.has_key(event):
                    d.queue.append((0, event, None))
                    # log.debug('wakeup (remove)')
                    win32event.SetEvent(d.wakeup)

                    return

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

        with self.mutex:
            for d in self.reactors:
                d.stop()

        for d in self.reactors:
            d.join()

    def start(self):
        """Start the reactor in a new thread."""

        threading.Thread.start(self)
        self.start_workers()

    def run(self):
        """Run the reactor in the current thread."""
        
        with self.mutex:
            self.start_workers()
            wait = self.timer.time_to_wait()

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

            with self.mutex:
                todo = self.queue
                self.queue = []
                timers = self.timer.get_pending()
                wait = self.timer.time_to_wait()

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
            

        

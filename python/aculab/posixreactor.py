# Copyright (C) 2002-2008 Lars Immisch

"""Reactor implementation for Posix systems that have poll()."""

from __future__ import with_statement

import threading
import select
import os
import logging
# local imports
from util import create_pipe
from timer import TimerBase

log = logging.getLogger('reactor')

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
        self.timer = TimerBase()

        # create a pipe to add/remove fds
        self.pipe = create_pipe()
        self.setDaemon(1)
        self.poll = select.poll()

        # listen to the read fd of our pipe
        self.poll.register(self.pipe[0], select.POLLIN)

    def add_timer(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.'''

        with self.mutex:
            t, adjust = self.timer.add(interval, function, args, kwargs)

        # if the new timer is the next, wake up the timer thread to readjust
        # the wait period

        if adjust and threading.currentThread() != self and self.isAlive():
            # function 2 is timer adjust
            self.pipe[1].write('2')

        return t

    def cancel_timer(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError'''
        with self.mutex:
            adjust = self.timer.cancel(timer)
        
        if adjust and threading.currentThread() != self and self.isAlive():
            # function 2 is timer adjust
            self.pipe[1].write('2')

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
            with self.mutex:
                self.handles[handle] = method
                # function 1 is add
                self.queue.append((1, handle, mode))

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
            with self.mutex:
                del self.handles[handle]
                # function 0 is remove
                self.queue.append((0, handle, None))

            self.pipe[1].write('0')

    def update(self):
        """Update our list of fds."""
        
        with self.mutex:
            add, fd, mask = self.queue.pop(0)

        if add:
            self.poll.register(fd, mask)
        else:
            self.poll.unregister(fd)

    def run_timers(self):
        """Run the pending timers.

        @return: time to wait for the next timer.
        """
        with self.mutex:
            timers = self.timer.get_pending()
            wait = self.timer.time_to_wait()

        for t in timers:
            t()

        return wait

    def run(self):
        'Run the reactor.'

        wait = self.timer.time_to_wait()
        
        while True:
            try:
                # log.debug('poll(%s)', wait)
                active = self.poll.poll(wait)
                for a, mask in active:
                    if a == self.pipe[0].fileno():
                        self.pipe[0].read(1)
                        wait = self.update()
                    else:
                        with self.mutex:
                            m = self.handles.get(a, None)

                        # log.info('event on fd %d %s: %s', a,
                        #         maskstr(mask), m.__name__)

                        # ignore missing method, it must have been removed
                        if m:
                            m()
                            
                wait = self.run_timers()

            except StopIteration:
                return
            except KeyboardInterrupt:
                return
            except:
                log.error('error in PollReactor main loop', exc_info=1)
                raise

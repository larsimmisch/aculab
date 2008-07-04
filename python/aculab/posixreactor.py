# Copyright (C) 2002-2008 Lars Immisch

"""Reactor implementation for Posix systems that have poll()."""

import threading
import select
import os
import logging
# local imports
from util import create_pipe

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

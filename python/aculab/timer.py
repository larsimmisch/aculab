# Copyright (C) 2003-2008 Lars Immisch

"""A thread-based timer"""

import threading
import time

class Timer:
    """A timed function and its arguments."""
    
    def __init__(self, interval, function, args=[], kwargs={}):
        self.absolute = time.time() + interval
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def __cmp__(self, other):
        return cmp(self.absolute, other.absolute)

    def __call__(self):
        self.function(*self.args, **self.kwargs)

class TimerBase:
    """Timer base class - does the housekeeping."""

    def __init__(self):
        self.timers = []

    def add(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.

        @return: the tuple (timer, flag). flag is True if the timer added
        is the next timer due.'''
        
        t = Timer(interval, function, args, kwargs)

        self.timers.append(t)
        self.timers.sort()

        return (t, self.timers.index(t) == 0)

    def cancel(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError.

        @return: True if the cancelled timer is the next timer due.'''

        i = self.timers.index(timer)
        del self.timers[i]

        return i == 0

    def time_to_wait(self):
        """Return the time to wait for the next timer in seconds or None
        if no timer is present."""
        if not self.timers:
            return None
        
        now = time.time()
        t = self.timers[0]
        
        return max(0.0, t.absolute - now)

    def get_pending(self):
        """Return a list of pending timers."""
        exp = []
        now = time.time()

        if self.timers:
            t = self.timers[0]
            while t.absolute <= now:
                exp.append(t)
                del self.timers[0]

                if not self.timers:
                    return exp
                
                t = self.timers[0]

        return exp
            
        
class TimerThread(threading.Thread, TimerBase):
    """An active, standalone Timer thread that will execute the
    timers in the context of its thread.

    In the context of pyAculab, this is mostly a test case for L{TimerBase}.

    In most cases, if you need timers, use the reactor instead."""
    
    def __init__(self):
        threading.Thread.__init__(self)
        TimerBase.__init__(self)
        self.setDaemon(1)
        self.event = threading.Event()
        self.mutex = threading.Lock()

    def add(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.'''

        self.mutex.acquire()
        try:
            t, adjust = TimerBase.add(self, interval, function, args, kwargs)
        finally:
            self.mutex.release()

        # if the new timer is the next, wake up the timer thread to readjust
        # the wait period
        if adjust:
            self.event.set()

        return t
        
    def cancel(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError'''
        self.mutex.acquire()
        try:
            adjust = TimerBase.cancel(self, timer)
        finally:
            self.mutex.release()
        
        if adjust:
            self.event.set()
            
    def run(self):
        '''Run the Timer in the current thread.
        If you want to run the Timer in its own thread, call start()'''
        while True:
            self.mutex.acquire()
            try:
                todo = self.get_pending()
                next = self.time_to_wait()
            finally:
                self.mutex.release()

            for t in todo:
                t()

            if next is not None:
                self.event.wait(next)
            else:
                self.event.wait()

            self.event.clear()

if __name__ == '__main__':

    def _test(id):
        print 'timer', id, 'fired'

    print 'expect 3 timers firing with 1 sec delay between them...'
    timer = TimerThread()

    timer.start()

    timer.add(3.0, _test, '3')
    t = timer.add(2.0, _test, '2')
    timer.cancel(t)
    # cancelling a timer twice raises a ValueError
    try:
        timer.cancel(t)
    except ValueError:
        pass
    t = timer.add(1.0, _test, '1')
    timer.cancel(t)
    timer.add(1.0, _test, '1')    
    timer.add(2.0, _test, '2')

    for i in range(4):
        time.sleep(1.0)

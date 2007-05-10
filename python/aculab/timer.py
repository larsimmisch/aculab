"""A thread-based timer"""

import threading
import time

class Timer:
    
    def __init__(self, interval, function, args=[], kwargs={}):
        self.absolute = time.time() + interval
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def __cmp__(self, other):
        return cmp(self.absolute, other.absolute)

class TimerThread(threading.Thread):
   
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(1)
        self.event = threading.Event()
        self.mutex = threading.Lock()
        self.timers = []

    def add(self, interval, function, args = [], kwargs={}):
        '''Add a timer after interval in seconds.'''
        t = Timer(interval, function, args, kwargs)

        self.mutex.acquire()
        try:
            self.timers.append(t)
            self.timers.sort()
            i = self.timers.index(t)
        finally:
            self.mutex.release()

        # if the new timer is the next, wake up the timer thread to readjust
        # the wait period
        if i == 0:
            self.event.set()

        return t
        
    def cancel(self, timer):
        '''Cancel a timer.
        Cancelling an expired timer raises a ValueError'''
        self.mutex.acquire()

        # if the deleted timer was the next, wake up the timer thread to
        # readjust the wait period
        try:
            i = self.timers.index(timer)
            del self.timers[i]
        finally:
            self.mutex.release()
        
        if i == 0:
            self.event.set()
            
    def run(self):
        '''Run the Timer in the current thread.
        If you want to run the Timer in its own thread, call start()'''
        while True:
            self.mutex.acquire()
            if self.timers:
                now = time.time()
                t = self.timers[0]
                if t.absolute <= now:
                    del self.timers[0]
                    self.mutex.release()
                    t.function(*t.args, **t.kwargs)
                        
                else:
                    self.mutex.release()
                    self.event.wait(t.absolute - now)
            else:
                self.mutex.release()
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

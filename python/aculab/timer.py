"""A timer thread class"""

import threading
import time

class Timer:
    
    def __init__(self, interval, function, args=[], kwargs={}):
        self.absolute = time.time() + interval
        self.function = function
        self.args = args
        self.kwargs = kwargs

def timer_sort(x, y):
    if x.absolute == y.absolute: return 0
    elif x.absolute < y.absolute: return -1
    else: return 1

class TimerThread(threading.Thread):
   
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(1)
        self.event = threading.Event()
        self.mutex = threading.Lock()
        self.timers = []

    def add(self, interval, function, args = [], kwargs={}):
        t = Timer(interval, function, args, kwargs)

        self.mutex.acquire()
        try:
            self.timers.append(t)
            self.timers.sort(timer_sort)
            i = self.timers.index(t)
        finally:
            self.mutex.release()
        
        if i == 0:
            self.event.set()

        return t
        
    def cancel(self, timer):
        self.mutex.acquire()
        try:
            i = self.timers.index(timer)
            del self.timers[i]
        finally:
            self.mutex.release()
        
        if i == 0:
            self.event.set()
            
    def run(self):
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

def _test(id):
    print 'timer', id, 'fired'

if __name__ == '__main__':
    
    timer = TimerThread()

    timer.start()

    t = timer.add(1.0, _test, '1')
    timer.cancel(t)
    timer.add(1.0, _test, '1')    
    t = timer.add(2.0, _test, '2')
    timer.cancel(t)
    timer.add(2.0, _test, '2')
    timer.add(3.0, _test, '3')

    for i in range(4):
        time.sleep(1.0)

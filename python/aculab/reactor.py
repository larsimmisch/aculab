"""Various reactors for Windows and Unix."""

import threading
import select
import os
import lowlevel
import logging
from names import event_names

if os.name == 'nt':
    import pywintypes
    import win32api
    import win32event

log = logging.getLogger('reactor')

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

class _CallEventReactor:

    def __init__(self, verbose = True):
        self.calls = {}
        self.verbose = verbose

    # add must only be called from a dispatched event
    # - not from a separate thread
    def add(self, call):
        self.calls[call.handle] = call

    # remove must only be called from a dispatched event
    # - not from a separate thread
    def remove(self, call):
        del self.calls[call.handle]

    def run(self):
        event = lowlevel.STATE_XPARMS()
        
        while True:
            if not self.calls:
                return
            
            event.handle = 0
            event.timeout = 200

            rc = lowlevel.call_event(event)
            if rc:
                raise AculabError(rc, 'call_event')

            handled = ''
            
            # call the event handlers
            if event.handle:
                if event.state == lowlevel.EV_EXTENDED:
                    ev = ext_event_names[event.extended_state].lower()
                else:
                    ev = event_names[event.state].lower()

                call = self.calls.get(event.handle, None)
                if not call:
                    log.error('got event %s for nonexisting call 0x%x',
                              ev, event.handle)
                    continue
                
                mutex = getattr(call.user_data, 'mutex', None)
                if mutex:
                    mutex.acquire()

                mcall = None
                mcontroller = None

                try:
                    mcall = getattr(call, ev, None)
                    mcontroller = getattr(call.controllers[-1], ev, None)
                    

                    # compute description of handlers
                    if mcontroller and mcall:
                        handled = '(call, controller)'
                    elif mcontroller:
                        handled = '(controller)'
                    elif mcall:
                        handled = '(call)'
                    else:
                        handled = '(ignored)'

                    log.debug('%s %s %s', call.name, ev, handled)

                    # let the call handle events first
                    if mcall:
                        mcall()
                    # pass the event on to the controller
                    if mcontroller:
                        mcontroller(call, call.user_data)

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


CallReactor = _CallEventReactor()

# this class is only needed on Windows
class Win32ReactorThread(threading.Thread):
    """Helper thread for Win32SpeechEventReactor.
    
    WaitForMultipleObjects is limited to 64 objects,
    so multiple reactor threads are needed."""

    def __init__(self, mutex, handle = None, method = None):
        """Create a Win32DisptacherThread."""
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
        
class Win32SpeechEventReactor(object):
    """Prosody Event reactor for Windows.

    Manages multiple reactor threads if more than 64 event handles are used.
    Each SpeechChannel uses 3 event handles, so this happens quickly."""

    def __init__(self):
        self.mutex = threading.Lock()
        self.reactors = []
        self.running = False
        
    def add(self, handle, method, mask = None):
        """Add a new handle to the reactor.

        @param handle: The handle of the Event to watch.
        @param method: This will be called when the event is fired."""
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

    def remove(self, handle):
        """Remove a handle from the reactor.

        @param handle: The handle of the Event to watch."""
        
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

        
class PollSpeechEventReactor(threading.Thread):
    """Prosody Event reactor for Unix systems with poll(), most notably
    Linux."""

    def __init__(self):
        """Create a reactor."""
        threading.Thread.__init__(self)
        self.handles = {}
        self.mutex = threading.Lock()
        self.queue = []

        # create a pipe to add/remove fds
        pfds = os.pipe()
        self.pipe = (os.fdopen(pfds[0], 'rb', 0), os.fdopen(pfds[1], 'wb', 0))
        self.setDaemon(1)
        self.poll = select.poll()

        # listen to the read fd of our pipe
        self.poll.register(self.pipe[0], select.POLLIN )
        
    def add(self, handle, method, mask = select.POLLIN|select.POLLOUT):
        """Add a new handle to the reactor.

        @param handle: Typically the C{tSMEventId} associated with the
            event, but any object with an C{fd} attribute will work also.
        @param method: This will be called when the event is fired.
        @param mask: Bitmask of POLLIN, POLLPRI, POLLOUT, POLLERR, POLLHUP
            or POLLNVAL or None for a default mask.
        
        add blocks until handle is added by reactor thread"""
        h = handle.fd
        if threading.currentThread() == self or not self.isAlive():
            # log.debug('adding fd: %d %s', h, method.__name__)
            self.handles[h] = method
            self.poll.register(h, mask)
        else:
            # log.debug('self adding: %d %s', h, method.__name__)
            event = threading.Event()
            self.mutex.acquire()
            self.handles[h] = method
            # function 1 is add
            self.queue.append((1, h, event, mask))
            self.mutex.release()
            self.pipe[1].write('1')
            event.wait()

    def remove(self, handle):
        """Remove a handle from the reactor.

        @param handle: Typically the C{tSMEventId} associated with the
        event, but any object with an C{fd} attribute will work also.
        
        This method blocks until handle is removed by the reactor thread."""
        h = handle.fd
        if threading.currentThread() == self or not self.isAlive():
            # log.debug('removing fd: %d', h)
            del self.handles[h]
            self.poll.unregister(h)
        else:
            # log.debug('removing fd: %d', h)
            event = threading.Event()
            self.mutex.acquire()
            del self.handles[h]
            # function 0 is remove
            self.queue.append((0, h, event, None))
            self.mutex.release()
            self.pipe[1].write('0')        
            event.wait()

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
                            add, fd, event, mask = self.queue.pop(0)
                        finally:
                            self.mutex.release()
                        if add:
                            self.poll.register(fd, mask)
                        else:
                            self.poll.unregister(fd)

                        if event:
                            event.set()
                    else:
                        self.mutex.acquire()
                        try:
                            m = self.handles.get(a, None)
                        finally:
                            self.mutex.release()

                        #log.info('event on fd %d %s: %s', a, maskstr(mask),
                        #         m.__name__)
                        
                        # ignore method not found
                        if m:
                            m()

            except StopIteration:
                return
            except KeyboardInterrupt:
                raise
            except:
                log.error('error in PollSpeechEventReactor main loop',
                          exc_info=1)

if os.name == 'nt':
    SpeechReactor = Win32SpeechEventReactor()
else:
    SpeechReactor = PollSpeechEventReactor()

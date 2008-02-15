# Copyright (c) 2001-2004 Twisted Matrix Laboratories for OrderedDict
# Copyright (C) 2003-2007 Lars Immisch

"""Utility classes: L{OrderedDict}, L{Lockable} and L{EventQueue}."""

import os
import lowlevel

# check driver info and create prosody streams if TiNG detected
_driver_info = lowlevel.SM_DRIVER_INFO_PARMS()
lowlevel.sm_get_driver_info(_driver_info)
TiNG_version = (_driver_info.major, _driver_info.minor)
del _driver_info

if os.name == 'nt':
    import pywintypes

def swig_value(s):
    a = s.find('_')
    if a != -1:
        o = s.find('_', a+1)
        return s[a+1:o]

    return s            

def os_event(event):
    if os.name == 'nt':
        return 

    return event.fd

def translate_card(card, module):
    if TiNG_version[0] < 2:
        return card, module

    from snapshot import Snapshot

    if type(card) == type(0):
        c = Snapshot().prosody[card]
    else:
        c = card

    if type(module) == type(0):
        m = c.modules[module]
    else:
        m = module

    return c, m

class OrderedDict(dict):
    """A UserDict that preserves insert order whenever possible."""
    def __init__(self, d=None, **kwargs):
        self._order = []
        self.data = {}
        if d is not None:
            if hasattr(d, 'keys'):
                self.update(d)
            else:
                for k,v in d: # sequence
                    self[k] = v
        if len(kwargs):
            self.update(kwargs)
            
    def __repr__(self):
        return '{'+', '.join([('%r: %r' % item) for item in self.items()])+'}'

    def __setitem__(self, key, value):
        if not self.has_key(key):
            self._order.append(key)
        dict.__setitem__(self, key, value)

    def copy(self):
        return self.__class__(self)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._order.remove(key)

    def iteritems(self, reverse = False):
        if not reverse:
            for item in self._order:
                yield (item, self[item])
        else:
            for item in reversed(self._order):
                yield (item, self[item])
                
    def items(self):
        return list(self.iteritems())

    def itervalues(self, reverse = False):
        if not reverse:
            for item in self._order:
                yield self[item]
        else:
            for item in reversed(self._order):
                yield self[item]

    def values(self):
        return list(self.itervalues())

    def iterkeys(self):
        return iter(self._order)

    def keys(self):
        return list(self._order)

    def popitem(self):
        key = self._order[-1]
        value = self[key]
        del self[key]
        return (key, value)

    def setdefault(self, item, default):
        if self.has_key(item):
            return self[item]
        self[item] = default
        return default

    def update(self, d):
        for k, v in d.items():
            self[k] = v

class Lockable(object):
    
    def __init__(self, mutex = None):
        self.mutex = mutex
    
    def lock(self):
        if self.mutex:
            self.mutex.acquire()

    def unlock(self):
        if self.mutex:
            self.mutex.release()

class EventQueue(object):

    def __init__(self):
        '''Allocate an event queue.'''
        q = lowlevel.ACU_ALLOC_EVENT_QUEUE_PARMS()
        rc = lowlevel.acu_allocate_event_queue(q)
        if rc:
            raise AculabError(rc, 'acu_allocate_event_queue')

        self.queue_id = q.queue_id

        wo = lowlevel.ACU_QUEUE_WAIT_OBJECT_PARMS()
        wo.queue_id = self.queue_id

        rc = lowlevel.acu_get_event_queue_wait_object(wo)
        if rc:
            raise AculabError(rc, 'acu_get_event_queue_wait_object')
        
        self.fd = wo.wait_object
        
    def __del__(self):
        f = lowlevel.ACU_FREE_EVENT_QUEUE_PARMS()
        f.queue_id = qid

        rc = lowlevel.acu_free_event_queue(f)
        if rc:
            raise AculabError(rc, 'acu_free_event_queue')


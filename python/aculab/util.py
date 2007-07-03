"""Utility classes: L{OrderedDict} and L{Lockable}."""

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
        return pywintypes.HANDLE(event)

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

    def iteritems(self):
        for item in self._order:
            yield (item, self[item])

    def items(self):
        return list(self.iteritems())

    def itervalues(self):
        for item in self._order:
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

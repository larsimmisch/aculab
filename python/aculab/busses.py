import sys
import lowlevel
import logging
from error import AculabError

log = logging.getLogger('switch')

class Connection:
    """A connection across a bus"""

    def __init__(self, bus):
        """If bus is None, the default bus is used."""
        if not bus:
            self.bus = DefaultBus
        else:
            self.bus = bus
        self.connections = []
        self.timeslots = []

    def close(self):
        """Closes the endpoint connections and frees the timeslots."""
        for c in self.connections:
            c.close()

        self.connections = []

        for t in self.timeslots:
            self.bus.free(t)

        self.timeslots = []

    def __del__(self):
        if self.connections or self.timeslots:
            self.close()

class CTBusConnection:

    def __init__(self, sw, ts):
        self.sw = sw
        self.ts = ts

    def close(self):
        """Disables a timeslot."""
        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.ts[0]
        output.ots = self.ts[1]
        output.mode = lowlevel.DISABLE_MODE

        rc = lowlevel.sw_set_output(self.sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        log.debug('%02d:%02d disabled' % self.ts)

        self.sw = None

    def __del__(self):
        if self.sw:
            self.close()

    def __repr__(self):
        return '<CTBusConnection [' + str(self.sw) + ', ' + str(self.ts) + ']>'

class CTBus(object):
    """Base class for an isochronous, multiplexed bus.
    An instance represents a collection of available timeslots."""

    def allocate(self):
        """Allocate a timeslot."""
        return self.slots.pop(0)

    def free(self, slot):
        """Free a timeslot"""
        self.slots.append(slot)

    def listen_to(self, switch, sink, source):
        """sink and source are tuples of timeslots.
           and returns a CTBusConnection.
           Do not discard the return value - it will dissolve
           the connection when it's garbage collected."""

        output = lowlevel.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        rc = lowlevel.sw_set_output(switch, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        return CTBusConnection(switch, sink)

class ProsodyLocalBus(CTBus):
    """An instance of this class represents the timeslots on
    Aculab-specific streams for one Prosody DSP.
    """

    def __init__(self, stream):
        self.slots = []
        for st in range(stream, stream + 2):
            for ts in range(32):
                self.slots.append((st, ts))

class MVIP(CTBus):
    """MVIP Bus.
    An instance of this class represents 16 streams of 32 unidirectional
    timeslots per stream.

    This is in contrast to the original MVIP switching model that
    exposes 8 streams with 32 bidirectional timelots.

    The original MVIP switching model does this by treating 'trunk' and
    'resource' cards differently with regards to the stream numbering.

    Applications need to be aware of this difference. Caveat implementor.
    """

    def __init__(self):
        self.slots = []
        for st in range(16):
            for ts in range(32):
                self.slots.append((st, ts))

    def invert(self, slot):
        if slot[0] < 8:
            return (slot[0] + 8, slot[1])
        else:
            return (slot[0] - 8, slot[1])

class SCBus(CTBus):
    """SCBus, Dialogic's successor of PEB.
    An instance of this class represents 1024 unidirectional timelots on
    stream 24 according to Aculab's stream numbering convention"""

    def __init__(self):
        self.slots = []
        for ts in range(1024):
            self.slots.append((24, ts))

class H100(CTBus):
    """H.100, the ECTF defined bus standard.
    This class also applies to H.110.
    An instance of this class represents 32 streams with 128 unidirectional
    timeslots per stream."""

    def __init__(self):
        self.slots = []
        for st in range(32):
            for ts in range(128):
                self.slots.append((st, ts))

_DefaultBus = None

def DefaultBus():
    """Returns the same instance of a CTbus subclass on every call (singleton).

    Unless a particular bus type can be deduced, the order of preference is:

    - H100
    - SCBus
    - MVIP"""

    if _DefaultBus:
        return _DefaultBus

    if lowlevel.cc_version == 5:
        sw = range(lowlevel.sw_get_drvrs())
    else:
        from snapshot import Snapshot
        sw = [s.open.card_id for s in Snapshot().switch]
        
    busses = 0
    
    # first, determine which busses are available on all cards
    for s in sw:
        mode = lowlevel.SWMODE_PARMS()
        rc = lowlevel.sw_mode_switch(s, mode)
        if rc:
            raise AculabError(rc, 'sw_mode_switch')

        busses |= mode.ct_buses

    # check if any card is sourced from MVIP or SCBus or drives SCBus
    for s in sw:
        clock = lowlevel.QUERY_CLKMODE_PARMS()
        rc = lowlevel.sw_query_clock_control(s, clock)
        if rc:
            raise AculabError(rc, 'sw_query_clock_control')

        if clock.last_clock_mode == lowlevel.CLOCK_REF_MVIP:
            return MVIP()
        elif clock.last_clock_mode & lowlevel.DRIVE_SCBUS or \
                 clock.last_clock_mode == lowlevel.CLOCK_REF_SCBUS:
            return SCBus()

    if busses & (1 << lowlevel.SWMODE_CTBUS_H100):
        return H100()

    if busses & (1 << lowlevel.SWMODE_CTBUS_SCBUS):
        return SCBus()

    if busses & (1 << lowlevel.SWMODE_CTBUS_MVIP):
        return MVIP()
    
    return None    

if __name__ == '__main__':
    print DefaultBus()

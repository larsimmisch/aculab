import sys
import lowlevel
import logging
from error import AculabError

log = logging.getLogger('switch')

class Connection:
    """A connection, potentially across a bus"""

    def __init__(self, bus):
        """If bus is None, the default bus is used."""
        if not bus:
            self.bus = DefaultBus
        else:
            self.bus = bus
        self.connections = []
        self.timeslots = []

    def close(self):
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
        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.ts[0]
        output.ots = self.ts[1]
        output.mode = lowlevel.DISABLE_MODE

        # print 'disabling', self.ts

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

class CTBus:
    """Base class for a isochronous, multiplexed bus."""

    def allocate(self):
        return self.slots.pop(0)

    def free(self, slot):
        self.slots.append(slot)

    def listen_to(self, switch, sink, source):
        """sink and source are tuples of timeslots.
           and returns a CTBusConnection.
           Do not discard the return value - it will dissolve
           the connection when it's garbage collected"""

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

class MVIP(CTBus):

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

    def __init__(self):
        self.slots = []
        for ts in range(1024):
            self.slots.append((24, ts))

class H100(CTBus):

    def __init__(self):
        self.slots = []
        for st in range(32):
            for ts in range(128):
                self.slots.append((st, ts))

class ProsodyLocalBus(CTBus):
    def __init__(self, module):
        self.slots = []
        for st in range(48 + module * 2, 50 + module * 2):
            for ts in range(32):
                self.slots.append((st, ts))

def _autodetect():
    """autodetects running (i.e. supported and clocked) busses and returns
    the CTBus subclass deemed best"""

    n = lowlevel.sw_get_drvrs()

    buses = 0
    
    # first, determine which busses are available on all cards
    for i in range(n):
        mode = lowlevel.SWMODE_PARMS()
        rc = lowlevel.sw_mode_switch(i, mode)
        if rc:
            raise AculabError(rc, 'sw_mode_switch')

        buses |= mode.ct_buses

    # check if any card is sourced from MVIP or SCBus or drives SCBus
    for i in range(n):
        clock = lowlevel.QUERY_CLKMODE_PARMS()
        rc = lowlevel.sw_query_clock_control(i, clock)
        if rc:
            raise AculabError(rc, 'sw_query_clock_control')

        if clock.last_clock_mode == lowlevel.CLOCK_REF_MVIP:
            return MVIP()
        elif clock.last_clock_mode & lowlevel.DRIVE_SCBUS or \
                 clock.last_clock_mode == lowlevel.CLOCK_REF_SCBUS:
            return SCBus()

    if buses & (1 << lowlevel.SWMODE_CTBUS_H100):
        return H100()

    if buses & (1 << lowlevel.SWMODE_CTBUS_SCBUS):
        return SCBus()

    if buses & (1 << lowlevel.SWMODE_CTBUS_MVIP):
        return MVIP()
    
    return None    
    
DefaultBus = _autodetect()
        

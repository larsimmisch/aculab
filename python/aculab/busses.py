'''Connection endpoints, Connection objects and CT busses.'''

import sys
import lowlevel
import logging
from error import AculabError

log = logging.getLogger('switch')

class CTBusEndpoint:
    """An endpoint on a bus.

    Endpoints are used to close a L{Connection}. They do all their work in
    C{close} or upon destruction (which calls C{close}).
    """
    def __init__(self, sw, ts):
        self.sw = sw
        self.ts = ts

    def close(self):
        """Disable the endpoint."""
        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.ts[0]
        output.ots = self.ts[1]
        output.mode = lowlevel.DISABLE_MODE

        rc = lowlevel.sw_set_output(self.sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d:%d, DISABLE_MODE)'
                              % (self.ts[0], self.ts[1]))

        log.debug('%02d:%02d disabled' % self.ts)

        self.sw = None
        self.ts = None

    def __del__(self):
        if self.ts:
            self.close()

    def __repr__(self):
        return 'CTBusEndpoint(' + str(self.sw) + ', ' + str(self.ts) + ')'

class NetEndpoint:
    """An endpoint on a network port.

    Endpoints are used to close a L{Connection}. They do all their work in
    C{close} or upon destruction (which calls C{close}).
    """
    def __init__(self, sw, port, ts):
        """Initialize an endpoint.

        @param sw: Handle for the switch card. On v6, this is an
        C{ACU_CARD_ID}, on v5, this is an index to the card.
        @param port: The network port. On v6, this is an C{ACU_PORT_ID}, on v5,
        it is the index of the module (restarts at zero for each new card)
        @param ts: A tuple (stream, timeslot)
        """
        self.sw = sw
        self.ts = ts
        # precompute silence pattern
        if lowlevel.call_line(port) == lowlevel.L_E1:
            self.pattern = 0x55 # alaw silence
        else:
            self.pattern = 0xff # mulaw silence
            
    def close(self):
        """Disable the endpoint.

        This method will assert a silence pattern on the network timeslot.

        The silence pattern (alaw or mulaw) is inferred from the line type
        via C{call_line}. E1 ports are assumed to be alaw, everything else
        mulaw."""
        
        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.ts[0]
        output.ots = self.ts[1]
        output.mode = lowlevel.PATTERN_MODE
        output.pattern = self.pattern

        rc = lowlevel.sw_set_output(self.sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d:%d, PATTERN_MODE, 0x%x)'
                              % (self.ts[0], self.ts[1], output.pattern))

        log.debug('%02d:%02d silenced' % self.ts)

        self.sw = None
        self.ts = None

    def __del__(self):
        """Close the endpoint if it is still open"""
        if self.ts:
            self.close()

    def __repr__(self):
        """Print a representation of the endpoint."""
        return 'NetEndpoint(' + str(self.port) + ', ' + str(self.ts) + ')'

class SpeechEndpoint(object):
    """An endpoint to a DSP.

    Endpoints are used to close a L{Connection}. They do all their work in
    C{close} or upon destruction (which calls C{close}).
    """
    
    def __init__(self, channel, direction):
        """Initialize an endpoint to a L{SpeechChannel}.

        @param channel: a L{SpeechChannel}.
        @param direction: Either I{in} or I{out}. Only used for logging.
        """
        self.channel = channel
        self.direction = direction
        if direction not in ['in', 'out', 'datafeed']:
            raise ValueError("direction must be 'in', 'out' or 'datafeed'")

    def close(self):
        """Disconnect the endpoint."""
        
        if self.channel:
            if self.direction == 'datafeed':
                connect = lowlevel.SM_CHANNEL_DATAFEED_CONNECT_PARMS()
                connect.channel = self.channel.channel
                # kSMNullDatafeedId isn't wrapped for some reason
                # connect.data_source= lowlevel.kSMNullDatafeedId
                
                rc = lowlevel.sm_channel_datafeed_connect(connect)
                if rc:
                    raise AculabSpeechError(rc, 'sm_channel_datafeed_connect')
                    
            else:
                input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

                input.channel = self.channel.channel
                input.st = -1
                input.ts = -1
                
                if self.direction == 'in':
                    rc = lowlevel.sm_switch_channel_input(input)
                    if rc:
                        raise AculabSpeechError(rc, 'sm_switch_channel_input')
                    else:
                        rc = lowlevel.sm_switch_channel_output(input)
                        if rc:
                            raise AculabSpeechError(
                                rc, 'sm_switch_channel_output')
                        
            log.debug('%s disconnected(%s)', self.channel.name, self.direction)

            self.channel = None

    def __del__(self):
        """Close the endpoint if it is still open"""        
        self.close()

    def __repr__(self):
        """Print a representation of the endpoint."""
        return 'SpeechEndpoint(%s, %s)'% (self.channel.name, self.direction)

class VMPtxEndpoint(object):
    """An endpoint to a VMPtx (RTP transmitter).

    Endpoints are used to close a L{Connection}. They do all their work in
    C{close} or upon destruction (which calls C{close}).
    """
    
    def __init__(self, vmptx):
        """Initialize a datafeed endpoint to a L{VMPtx}.

        @param vmptx: a L{VMPtx}.
        """
        self.vmptx = vmptx

    def close(self):
        """Disconnect the endpoint."""
        
        if self.vmptx:
            connect = lowlevel.SM_VMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.vmptx.vmptx
            # connect.data_source= lowlevel.kSMNullDatafeedId

            rc = lowlevel.sm_vmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_vmptx_datafeed_connect')

            self.vmptx = None

    def __del__(self):
        """Close the endpoint if it is still open"""
        
        self.close()

    def __repr__(self):
        """Print a representation of the endpoint."""
        
        return 'VMPtxEndpoint(%s)'% self.vmptx.name    

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
        """sink and source are tuples of (stream, timeslots).
        returns a CTBusEndpoint.
        Do not discard the return value - it will disconnect the endpoint
        when it is garbage collected."""

        output = lowlevel.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        rc = lowlevel.sw_set_output(switch, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        return CTBusEndpoint(switch, sink)

class ProsodyTimeslots(CTBus):
    """The timeslots for one Prosody DSP."""

    def __init__(self, stream):
        """Create the timeslots for a Prosody DSP.

        @param stream: The stream number, taken from C{SM_MODULE_INFO_PARMS}"""
        self.slots = []
        for st in range(stream, stream + 2):
            for ts in range(32):
                self.slots.append((st, ts))

class MVIP(CTBus):
    """MVIP Bus.
    An instance of this class represents 8 streams of 32 bidirectional
    timeslots per stream.

    This is *totally* different from H.100 and SCBus, where the timeslots
    are unidirectional.

    This is a consequence of the MVIP switching model that, among other things,
    attempted to simplify things by treating 'trunk' and 'resource' cards
    differently with regards to the stream numbering.

    Applications need to be aware of this difference. Don't use this bus unless
    you have to.
    """

    def __init__(self):
        self.slots = []
        for st in range(8):
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
    """H.100 (and H.110), the ECTF defined bus standards.

    An instance of this class represents 32 streams with 128 unidirectional
    timeslots per stream."""

    def __init__(self):
        self.slots = []
        for st in range(32):
            for ts in range(128):
                self.slots.append((st, ts))

_DefaultBus = None

def DefaultBus():
    """Singleton: Return the sanest bus supported by the hardware.
    
    If more than one bus type is supported by all cards, the order of
    preference is:
     - H100
     - SCBus
     - MVIP
    """

    global _DefaultBus

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
            _DefaultBus = MVIP()
            return _DefaultBus
        elif clock.last_clock_mode & lowlevel.DRIVE_SCBUS or \
                 clock.last_clock_mode == lowlevel.CLOCK_REF_SCBUS:
            _DefaultBus = SCBus()
            return _DefaultBus

    if busses & (1 << lowlevel.SWMODE_CTBUS_H100):
        _DefaultBus = H100()

    if busses & (1 << lowlevel.SWMODE_CTBUS_SCBUS):
        _DefaultBus = SCBus()

    if busses & (1 << lowlevel.SWMODE_CTBUS_MVIP):
        _DefaultBus = MVIP()
    
    return _DefaultBus

class Connection:
    """A connection between two resources.

    A connection consists of endpoints and timeslots.
    
    This class takes care of closing the contained endpoints and bus
    timeslots in the proper order upon destruction."""

    def __init__(self, bus = DefaultBus(), endpoints = [], timeslots = []):
        """If bus is None, the default bus is used."""
        self.bus = bus
        self.endpoints = endpoints
        self.timeslots = timeslots

    def close(self):
        """Close the connection and free all resources.

        Closes the contained endpoints and frees the timeslots.
        Endpoints are closed in reversed order to avoid clicks."""
        for c in reversed(self.endpoints):
            c.close()

        self.endpoints = []

        for t in self.timeslots:
            self.bus.free(t)

        self.timeslots = []

    def __del__(self):
        if self.endpoints or self.timeslots:
            self.close()

if __name__ == '__main__':
    print DefaultBus()

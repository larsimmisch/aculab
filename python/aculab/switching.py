# Copyright (C) 2002-2007 Lars Immisch

"""L{connect} and support classes.

This module contains Connection endpoints, Connection objects and CT busses."""

import sys
import lowlevel
import logging
from error import AculabError, AculabSpeechError
from util import translate_card

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

        log.debug('%02d:%02d disabled', self.ts[0], self.ts[1])

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

        if self.ts:
            output = lowlevel.OUTPUT_PARMS()
            output.ost = self.ts[0]
            output.ots = self.ts[1]
            output.mode = lowlevel.PATTERN_MODE
            output.pattern = self.pattern

            rc = lowlevel.sw_set_output(self.sw, output)
            if rc:
                raise AculabError(
                    rc, 'sw_set_output(%d:%d, PATTERN_MODE, 0x%x)'
                    % (self.ts[0], self.ts[1], output.pattern))

            log.debug('%02d:%02d silenced', self.ts[0], self.ts[1])

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
        @param direction: Either C{'rx'} or C{'tx'}. Only used for logging.
        """
        self.channel = channel
        self.direction = direction
        if direction not in ['rx', 'tx', 'datafeed']:
            raise ValueError("direction must be 'rx', 'tx' or 'datafeed'")

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
                
                if self.direction == 'rx':
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
    
    def __init__(self, vmptx, tdmrx = None):
        """Initialize a datafeed endpoint to a L{VMPtx}.

        @param vmptx: a L{VMPtx}.
        @param tdmrx: an optional L{TDMrx}.
        """
        self.vmptx = vmptx
        self.tdmrx = tdmrx

    def close(self):
        """Disconnect the endpoint."""

        if self.tdmrx:
            self.tdmrx.close()
            self.tdmrx = None
        
        if self.vmptx:
            connect = lowlevel.SM_VMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.vmptx.vmptx
            # connect.data_source = lowlevel.kSMNullDatafeedId

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

class FMPtxEndpoint(object):
    """An endpoint to a FMPtx (RTP T.38 transmitter).

    Endpoints are used to close a L{Connection}. They do all their work in
    C{close} or upon destruction (which calls C{close}).
    """
    
    def __init__(self, vmptx, tdmrx = None):
        """Initialize a datafeed endpoint to a L{FMPtx}.

        @param fmptx: a L{FMPtx}.
        @param tdmrx: an optional L{TDMrx}.
        """
        self.fmptx = fmptx
        self.tdmrx = tdmrx

    def close(self):
        """Disconnect the endpoint."""

        if self.tdmrx:
            self.tdmrx.close()
            self.tdmrx = None
        
        if self.fmptx:
            connect = lowlevel.SM_FMPTX_DATAFEED_CONNECT_PARMS()
            connect.vmptx = self.fmptx.vmptx
            # connect.data_source = lowlevel.kSMNullDatafeedId

            rc = lowlevel.sm_fmptx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(rc, 'sm_fmptx_datafeed_connect')

            self.fmptx = None

    def __del__(self):
        """Close the endpoint if it is still open"""
        
        self.close()

    def __repr__(self):
        """Print a representation of the endpoint."""
        
        return 'FMPtxEndpoint(%s)'% self.fmptx.name    

type_abbr = {lowlevel.kSMTimeslotTypeALaw: 'a',
             lowlevel.kSMTimeslotTypeMuLaw: 'm',
             lowlevel.kSMTimeslotTypeData: 'd' }

class TDMtx(object):
    """A TDM transmitter."""

    def __init__(self, ts, card = 0, module = 0):
        """Create a TDM transmitter.

        @param ts: a tuple (stream, timeslot, [timeslot_type])
        timeslot_type is optional.

        See U{sm_tdmtx_create
        <http://www.aculab.com/support/TiNG/gen/\
        apifn-sm_tdmtx_create.html>}.
        """

        self.card, self.module = translate_card(card, module)

        tdmtx = lowlevel.SM_TDMTX_CREATE_PARMS()
        tdmtx.module = self.module.open.module_id
        tdmtx.stream = ts[0]
        tdmtx.timeslot = ts[1]
        tdmtx.type = lowlevel.kSMTimeslotTypeData
        if len(ts) > 2:
            tdmtx.type = ts[2]

        rc = lowlevel.sm_tdmtx_create(tdmtx)
        if rc:
            raise AculabSpeechError(rc, 'sm_tdmtx_create')

        self.tdmtx = tdmtx.tdmtx
        self.name = 'tx-%d:%d%s' % (ts[0], ts[1], type_abbr[tdmtx.type])

    def close(self):
        """Destroy the TDM transmitter.
        
        See U{sm_tdmtx_destroy
        <http://www.aculab.com/support/TiNG/gen/\
        apifn-sm_tdmtx_destroy.html>}."""
        
        if self.tdmtx:
            rc = lowlevel.sm_tdmtx_destroy(self.tdmtx)
            self.tdmtx = None

    def listen_to(self, other):
        """Listen to another (datafeed) endpoint."""
        if hasattr(other, 'get_datafeed'):
            connect = lowlevel.SM_TDMTX_DATAFEED_CONNECT_PARMS()
            connect.tdmtx = self.tdmtx
            connect.data_source = other.get_datafeed()

            rc = lowlevel.sm_tdmtx_datafeed_connect(connect)
            if rc:
                raise AculabSpeechError(
                    rc, 'sm_tdmtx_datafeed_connect(%s)' % other.name,
                    self.name)

            log.debug('%s := %s', self.name, other.name)
        else:
            raise ValueError('%s := %s: cannot connect to instance without '\
                             'get_datafeed() method' % (self.name, other.name))

    def __repr__(self):
        return self.name

class TDMrx(object):
    """A TDM receiver."""
    
    def __init__(self, ts, card = 0, module = 0):
        """Create a TDM transmitter.

        @param ts: a tuple (stream, timeslot, [timeslot_type])
        timeslot_type is optional.

        See U{sm_tdmrx_create
        <http://www.aculab.com/support/TiNG/gen/\
        apifn-sm_tdmrx_create.html>}.
        """

        self.card, self.module = translate_card(card, module)
        # Initialize early
        self.tdmrx = None
        self.datafeed = None

        tdmrx = lowlevel.SM_TDMRX_CREATE_PARMS()
        tdmrx.module = self.module.open.module_id
        tdmrx.stream = ts[0]
        tdmrx.timeslot = ts[1]
        tdmrx.type = lowlevel.kSMTimeslotTypeData
        if len(ts) > 2 and ts[2] is not None:
            tdmrx.type = ts[2]

        rc = lowlevel.sm_tdmrx_create(tdmrx)
        if rc:
            raise AculabSpeechError(rc, 'sm_tdmrx_create')

        self.tdmrx = tdmrx.tdmrx
        self.name = 'rx-%d:%d%s' % (ts[0], ts[1], type_abbr[tdmrx.type])

        # get the datafeed
        datafeed = lowlevel.SM_TDMRX_DATAFEED_PARMS()

        datafeed.tdmrx = self.tdmrx
        rc = lowlevel.sm_tdmrx_get_datafeed(datafeed)
        if rc:
            raise AculabSpeechError(rc, 'sm_tdmrx_get_datafeed', self.name)

        self.datafeed = datafeed.datafeed

    def close(self):
        """Destroy the TDM receiver.

        See U{sm_tdmrx_destroy
        <http://www.aculab.com/support/TiNG/gen/\
        apifn-sm_tdmrx_destroy.html>}."""

        if self.tdmrx:
            rc = lowlevel.sm_tdmrx_destroy(self.tdmrx)
            self.datafeed = None
            self.tdmrx = None

    def get_datafeed(self):
        """Used internally by the switching protocol."""
        return self.datafeed

    def __repr__(self):
        return self.name

class CTBus(object):
    """Base class for an isochronous, multiplexed bus.
    An instance represents a collection of available timeslots."""

    def allocate(self, ts_type = None):
        """Allocate a timeslot."""
        return self.slots.pop(0) + (ts_type,)

    def free(self, slot):
        """Free a timeslot"""
        self.slots.append(slot[:2])

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

    The L{connect} function tries to take these differences into account, but
    it hasn't been tested in all possible combinations.

    In other words: don't use this bus unless you have to.
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

    def __init__(self, bus = DefaultBus(), endpoints = None, timeslots = None):
        """If bus is None, the default bus is used."""
        self.bus = bus
        if endpoints is None:
            self.endpoints = []
        else:
            self.endpoints = endpoints
        if timeslots is None:
            self.timeslots = []
        else:
            self.timeslots = timeslots

    def add(self, endpoint, timeslot = None):
        if endpoint:
            self.endpoints.append(endpoint)

        if timeslot:
            self.timeslots.append(timeslot)

    def close(self):
        """Close the connection and free all resources.

        Closes the contained endpoints and frees the timeslots.
        Endpoints are closed in reversed order to avoid clicks."""
        for e in reversed(self.endpoints):
            e.close()

        self.endpoints = []

        for t in self.timeslots:
            self.bus.free(t)

        self.timeslots = []

    def __del__(self):
        if self.endpoints or self.timeslots:
            self.close()

def connect(a, b, bus=DefaultBus(), force_bus=False):
    """Create a duplex connection between a and b.

    @param a: a duplex capable entity (like a CallHandle or a SpeechChannel)
    or a tuple of (tx, rx).
        
    @param b: a duplex capable entity (like a CallHandle or a SpeechChannel)
    or a tuple of (tx, rx).

    @return: A L{Connection} object containing all endpoints and timeslots
    allocated for the connection. This object will dissolve the
    connection when it is deleted.

    B{Note}: Ignoring the return value will immediately dissolve the
    connection. Don't do that.
    """

    # Connectable classes must implement:
    # 
    # - get_module: a unique identifier for the port/module. Care must be taken
    #   that call control and DSPs don't accidentally return interchangeable
    #   identifiers. The current scheme is:
    #
    #   On DSP entities, a SpeechModule instance is used for TiNG >= 2, and
    #   a tuple (card, module) on older TiNG versions
    #   Call control cards return the port offset on V5 or a Port instance
    #   on V6.
    #
    # - get_switch: a SwitchCard instance on V6, and a switch card offset on V5
    #
    # - get_datafeed: None or the datafeed
    #
    # - get_timeslot: None or the transmit timeslot

    c = Connection(bus)

    if type(a) == tuple:
        atx, arx = a[:2]
    else:
        atx = arx = a

    if type(b) == tuple:
        btx, brx = b[:2]
    else:
        btx = brx = b

    if not force_bus:
        # Optimizations first

        # TiNG version 2: same module, make datafeed connections
        # Doesn't apply to calls because they have no datafeeds
        if arx.get_module() == brx.get_module() \
               and atx.get_module() == btx.get_module() \
               and arx.get_datafeed() and brx.get_datafeed():
            c.connections = [atx.listen_to(brx), btx.listen_to(arx)]

            return c

        # Same card or module, connect directly
        if arx.get_switch() == brx.get_switch() \
               and atx.get_switch() == btx.get_switch() \
               or (atx.get_module() == brx.get_module() \
                   and btx.get_module() == arx.get_module()):
            c.endpoints = [atx.listen_to(brx.get_timeslot()),
                           btx.listen_to(arx.get_timeslot())]
            return c
        
    # The general case: allocate two timeslots...
    c.timeslots = [ bus.allocate(), bus.allocate() ]

    # ...and connect across the bus
    if isinstance(bus, MVIP):
        # we are brave, we even support MVIP

        # ad-hoc: Prosody ISA daughterboards don't obey the funny
        # MVIP stream numbering scheme
        if arx.get_switch() != -1 and brx.get_switch() != -1:
            c.endpoints = [ brx.speak_to(c.timeslots[0]),
                            atx.listen_to(bus.invert(c.timeslots[0])),
                            arx.speak_to(c.timeslots[1]),
                            btx.listen_to(bus.invert(c.timeslots[1])) ]

            return c
        
    # nonpathological case
    #c.endpoints = [ brx.speak_to(c.timeslots[0]),
    #                atx.listen_to(c.timeslots[0]),
    #                arx.speak_to(c.timeslots[1]),
    #                btx.listen_to(c.timeslots[1]) ]

    c.endpoints = [ bus.listen_to(brx.get_switch(), c.timeslots[0],
                                  brx.get_timeslot()),
                    atx.listen_to(c.timeslots[0]),
                    bus.listen_to(arx.get_switch(), c.timeslots[1],
                                  arx.get_timeslot()),
                    btx.listen_to(c.timeslots[1]) ]

    return c

if __name__ == '__main__':
    print DefaultBus()

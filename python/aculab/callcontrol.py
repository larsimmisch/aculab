import sys
import getopt
import lowlevel
import aculab
import logging
from busses import Connection, CTBusConnection, NetConnection, DefaultBus
from error import AculabError
from names import event_names

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


log = logging.getLogger('call')
log_switch = logging.getLogger('switch')

try:
    _versionp = lowlevel.CALL_API_VERSION_PARMS()
    lowlevel.call_api_version(_versionp)
    version = (_versionp.major, _versionp.minor, _versionp.rev)
    del _versionp
except AttributeError:
    rc = lowlevel.call_version(0)
    if rc < 0:
        raise AculabError(rc, 'call_version')
    version = ((rc & 0xff00) >> 8, rc & 0xff, '')

class _CallEventDispatcher:

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


CallDispatcher = _CallEventDispatcher()

class CallHandle:
    """The CallHandle class models a call handle, as defined by the Aculab
    lowlevel, and common operations on it. Some events are handled to maintain
    the internal state, but in general, event handling is delegated to the
    controller."""

    def __init__(self, controller, user_data = None, card = 0, port = 0,
                 timeslot = None, dispatcher = CallDispatcher):

        self.user_data = user_data
        # this is a stack of controllers
        self.controllers = [controller]
        self.dispatcher = dispatcher
        self.port = port

        # automatically translate port numbers to v6 port_ids
        if version[0] >= 6:
            if type(port) == type(0) and type(card) == type(0):
                from snapshot import Snapshot
                self.port = Snapshot().call[card].ports[port].open.port_id
            
        if not timeslot:
            self.timeslot = -1
        else:
            self.timeslot = timeslot

        self.switch = lowlevel.call_port_2_swdrvr(self.port)
        if self.switch < 0:
            raise AculabError(self.switch, 'call_port_2_swdrvr')
            
        self.handle = None
        self.name = '0x0000'
        self.details = lowlevel.DETAIL_XPARMS()
        # The dispatcher sets the last state changing event after dispatching
        # the event. Which events are deemed state changing is controlled via
        # no_state_change_events
        self.last_event = lowlevel.EV_IDLE
        self.last_extended_event = None

    def push_controller(self, controller):
        self.controllers.append(controller)

    def pop_controller(self):
        self.controllers.pop()

    def openin(self, unique_xparms = None, cnf = None):
        inparms = lowlevel.IN_XPARMS()
        inparms.net = self.port
        inparms.ts = self.timeslot
        if cnf:
            inparms.cnf = cnf
        else:
            inparms.cnf = lowlevel.CNF_REM_DISC
            if self.timeslot != -1:
                inparms.cnf |= lowlevel.CNF_TSPREFER
                
        if unique_xparms:
            inparms.unique_xparms = unique_xparms

        rc = lowlevel.call_openin(inparms)
        if rc:
            raise AculabError(rc, 'call_openin')

        self.handle = inparms.handle
        self.name = hex(self.handle)

        self.dispatcher.add(self)

        log.debug('%s openin()', self.name)

    def _outparms(self, destination_address, sending_complete = 1,
                  originating_address = '', unique = None,
                  feature = None, feature_data = None, cnf = None):
        
        if feature and feature_data:
            outparms = lowlevel.FEATURE_OUT_XPARMS()

            if cnf:
                outparms.cnf = cnf
            else:
                outparms.cnf = lowlevel.CNF_REM_DISC
                if self.timeslot != -1:
                    outparms.cnf |= lowlevel.CNF_TSPREFER

            outparms.feature_information = feature
            outparms.feature = feature_data
        else:
            outparms = lowlevel.OUT_XPARMS()
            outparms.cnf = lowlevel.CNF_REM_DISC
            if self.timeslot != -1:
                outparms.cnf |= lowlevel.CNF_TSPREFER
                
        outparms.net = self.port
        outparms.ts = self.timeslot
        outparms.sending_complete = sending_complete
        outparms.originating_addr = originating_address
        outparms.destination_addr = destination_address

        if unique:
            outparms.unique_xparms = unique
                
        return outparms

    def openout(self, destination_address, sending_complete = True,
                originating_address = '', unique = None,
                feature = None, feature_data = None, cnf = None):

        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, unique,
                                  feature, feature_data, cnf)
        
        if feature and feature_data:
            rc = lowlevel.call_feature_openout(outparms)
            if rc:
                raise AculabError(rc, 'call_feature_openout')
        else:
            rc = lowlevel.call_openout(outparms)
            if rc:
                raise AculabError(rc, 'call_openout')

        # it is permissible to do an openout after an openin
        # we save the handle from openin in this case
        if self.handle:
            self.in_handle = self.handle

        self.handle = outparms.handle
        self.name = hex(self.handle)

        self.dispatcher.add(self)

        log.debug('%s openout(%s, %d, %s)', self.name, destination_address,
                  sending_complete, originating_address)



    def feature_send(self, feature_type, message_control, feature):

        fp = lowlevel.FEATURE_DETAIL_XPARMS()
        fp.handle = self.handle
        fp.net = self.port
        fp.feature_type = feature_type
        fp.message_control = message_control
        fp.feature = feature

        rc = lowlevel.call_feature_send(fp)
        if rc:
            raise AculabError(rc, 'call_feature_send', self.handle)

        log.debug('%s call_feature_send(%d, %d)',
                  self.name, feature_type, message_control)

    def enquiry(self, destination_address, sending_complete = 1,
                originating_address = '',
                feature = None, feature_data = None, cnf = None):

        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, feature, feature_data,
                                  cnf)

        if feature and feature_data:
            rc = lowlevel.call_feature_enquiry(outparms)
            if rc:
                raise AculabError(rc, 'call_feature_enquiry', self.handle)
        else:
            rc = lowlevel.call_enquiry(outparms)
            if rc:
                raise AculabError(rc, 'call_enquiry', self.handle)

        # it is permissible to do an openout after an openin
        # we save the handle from openin in this case
        if self.handle and (self.handle & lowlevel.INCH):
            self.in_handle = self.handle

        self.handle = outparms.handle
        self.name = hex(self.handle)

        self.dispatcher.add(self)

        log.debug('%s enquiry(%s, %d, %s)', self.name, destination_address,
                  sending_complete, originating_address)

    def transfer(self, call):
        transfer = lowlevel.TRANSFER_XPARMS()
        transfer.handlea = self.handle
        transfer.handlec = call.handle
        
        rc = lowlevel.call_transfer(transfer)
        if rc:
            raise AculabError(rc, 'call_transfer', self.handle)
        
        log.debug('%s transfer(%s)', self.name, call.name)

    def hold(self):
        rc = lowlevel.call_hold(self.handle)
        if rc:
            raise AculabError(rc, 'call_hold', self.handle)

        log.debug('%s hold()', self.name)

    def reconnect(self):
        rc = lowlevel.call_reconnect(self.handle)
        if rc:
            raise AculabError(rc, 'call_reconnect', self.handle)

        log.debug('%s reconnect()', self.name)

    def send_overlap(self, addr, complete = 0):
        overlap = lowlevel.OVERLAP_XPARMS()
        overlap.handle = self.handle
        overlap.sending_complete = complete
        overlap.destination_addr = addr

        rc = lowlevel.call_send_overlap(overlap)
        if rc:
            raise AculabError(rc, 'call_send_overlap', self.handle)

        log.debug('%s send_overlap(%s, %d)', self.name, addr, complete)

    def send_keypad_info(self, keypad = '', display = ''):
        keypadx = lowlevel.KEYPAD_XPARMS()
        keypadx.handle = self.handle
        keypadx.unique_xparms.sig_q931.location = lowlevel.KEYPAD_CONNECT
        keypadx.unique_xparms.sig_q931.keypad.setie(keypad)
        keypadx.unique_xparms.sig_q931.display.setie(display)

        rc = lowlevel.call_send_keypad_info(keypadx)
        if rc:
            raise AculabError(rc, 'call_send_keypad_info')

    def listen_to(self, source):
        """source is a tuple of (stream, timeslot).
           Returns a NetConnection.
           Do not discard the return value - it will dissolve
           the connection when it is garbage collected"""

        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.details.stream
        output.ots = self.details.ts
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        rc = lowlevel.sw_set_output(self.switch, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d:%d := %d:%d)' %
                              (output.ost, output.ots, source[0], source[1]),
                              self.handle)

        log_switch.debug('%s [%d] %d:%d := %d:%d', self.name,
                         self.switch,
                         output.ost, output.ots,
                         output.ist, output.its)

        return NetConnection(self.port, (self.details.stream, self.details.ts))

    def speak_to(self, sink):
        """source is a tuple of (stream, timeslot).
           Returns a CTBusConnection.
           Do not discard the return value - it will dissolve
           the connection when it's garbage collected"""

        output = lowlevel.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = lowlevel.CONNECT_MODE
        output.ist = self.details.stream
        output.its = self.details.ts

        rc = lowlevel.sw_set_output(self.switch, output)
        if rc:
            raise AculabError(rc, 'sw_set_output(%d:%d := %d:%d)' %
                              (sink[0], sink[1], output.ist, output.its),
                              self.handle)

        log_switch.debug('%s [%d] %d:%d := %d:%d', self.name,
                         self.switch,
                         output.ost, output.ots,
                         output.ist, output.its)

        return CTBusConnection(self.switch, sink)

    def connect(self, other, bus = DefaultBus()):
        c = Connection(bus)
        if isinstance(other, CallHandle):
            # other is a CallHandle (or subclass)
            if self.switch == other.switch:
                # connect directly
                c.connections = [self.listen_to((other.details.stream,
                                                   other.details.ts)),
                                 other.listen_to((self.details.stream,
                                                  self.details.ts))]
            else:
                # allocate two timeslots
                c.timeslots = [ bus.allocate(), bus.allocate() ]
                # make connections
                c.connections = [ other.speak_to(c.timeslots[0]),
                                  self.listen_to(c.timeslots[0]),
                                  self.speak_to(c.timeslots[1]),
                                  other.listen_to(c.timeslots[1]) ]
        
        else:
            # other is a SpeechChannel (or subclass)
            if self.switch == other.info.card:
                # connect directly
                c.connections = [self.listen_to((other.info.ost,
                                                 other.info.ots)),
                                 other.listen_to((self.details.stream,
                                                  self.details.ts))]
            else:
                # allocate two timeslots
                c.timeslots = [ bus.allocate(), bus.allocate() ]
                # make connections
                c.connections = [ other.speak_to(c.timeslots[0]),
                                  self.listen_to(c.timeslots[0]),
                                  self.speak_to(c.timeslots[1]),
                                  other.listen_to(c.timeslots[1]) ]

        return c

    def get_cause(self):
        cause = lowlevel.CAUSE_XPARMS()
        cause.handle = self.handle
        rc = lowlevel.call_getcause(cause)
        if rc:
            raise AculabError(rc, 'call_details', self.handle)

        return cause
    
    def get_details(self):
        self.details = lowlevel.DETAIL_XPARMS()
        self.details.handle = self.handle

        rc = lowlevel.call_details(self.details)
        if rc:
            raise AculabError(rc, 'call_details', self.handle)

        return self.details

    def get_feature_details(self, type):
        self.feature_details = lowlevel.FEATURE_DETAIL_XPARMS()
        self.feature_details.handle = self.handle
        self.feature_details.feature_type = type

        rc = lowlevel.call_feature_details(self.feature_details)
        if rc:
            raise AculabError(rc, 'call_feature_details', self.handle)

        return self.feature_details

    def accept(self):
        """Accept the call."""
        rc = lowlevel.call_accept(self.handle)
        if rc:
            raise AculabError(rc, 'call_accept', self.handle)

        log.debug('%s accept()', self.name)

    def incoming_ringing(self):
        """Signal incoming ringing."""
        rc = lowlevel.call_incoming_ringing(self.handle)
        if rc:
            raise AculabError(rc, 'call_incoming_ringing', self.handle)

        log.debug('%s incoming_ringing()', self.name)

    def disconnect(self, cause = None):
        '''Disconnect a call. Cause may be a CAUSE_XPARMS struct or an int'''
        if cause is None:
            xcause = lowlevel.CAUSE_XPARMS()
            xcause.cause = lowlevel.LC_NORMAL
        elif type(cause) == type(0):
            xcause = lowlevel.CAUSE_XPARMS()
            xcause.cause = cause
        else:
            xcause = cause

        if self.handle:
            xcause.handle = self.handle

            rc = lowlevel.call_disconnect(xcause)
            if rc:
                raise AculabError(rc, 'call_disconnect', self.handle)

        log.debug('%s disconnect(%d)', self.name, xcause.cause)

    def release(self, cause = None):
        '''Release a call. Cause may be a CAUSE_XPARMS struct or an int'''

        self.dispatcher.remove(self)

        # reset details
        self.details = lowlevel.DETAIL_XPARMS()

        if self.handle:
            if cause is None:
                xcause = lowlevel.CAUSE_XPARMS()
            elif type(cause) == type(0):
                xcause = lowlevel.CAUSE_XPARMS()
                xcause.cause = cause
            else:
                xcause = cause

            xcause.handle = self.handle
            
            rc = lowlevel.call_release(xcause)
            if rc:
                raise AculabError(rc, 'call_release', self.handle)

        log.debug('%s release(%d)', self.name, xcause.cause)

        # restore the handle for the inbound call if there is one
        if hasattr(self, 'in_handle'):
            self.handle = self.in_handle
            self.name = hex(self.handle)
            del self.in_handle
        else:
            self.handle = None
            self.name = '0x0000'
            
    def ev_incoming_call_det(self):
        self.get_details()

    def ev_ext_hold_request(self):
        self.get_details()

    def ev_outgoing_ringing(self):
        self.get_details()

    def ev_call_connected(self):
        self.get_details()

    def ev_idle(self):
        self.get_feature_details(lowlevel.FEATURE_FACILITY)
        self.get_details()
        self.release()

class Call(CallHandle):
    """A Call is a CallHandle that does an automatic openin upon creation."""

    def __init__(self, controller, user_data = None, card = 0, port = 0,
                 timeslot = -1, dispatcher = CallDispatcher):
        
        CallHandle.__init__(self, controller, user_data,
                            card, port, timeslot, dispatcher)

        self.openin()

            

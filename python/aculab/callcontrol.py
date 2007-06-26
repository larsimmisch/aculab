"""Call Control - a thin layer on top of the Aculab API.

Terminology: a 'call' in this module should be called a 'call leg' according
to international treaties, but in Aculab's nomenclature, it's a call.
"""

import sys
import getopt
import lowlevel
import aculab
import logging
from reactor import CallReactor
from busses import Connection, CTBusEndpoint, NetEndpoint, DefaultBus
from error import AculabError

log = logging.getLogger('call')
log_switch = logging.getLogger('switch')

class CallHandleBase:
    """Base class for a Call Handle.

    Holds common members and the controller stack."""

    def __init__(self, controller, user_data = None, port = 0,
                 reactor = CallReactor):

        self.user_data = user_data
        # this is a stack of controllers
        self.controllers = [controller]
        self.reactor = reactor
        self.port = port

        self.handle = None
        self.name = 'Cch-0000'
        
        # The reactor sets the last state changing event after dispatching
        # the event. Which events are deemed state changing is controlled via
        # no_state_change_events
        self.last_event = lowlevel.EV_IDLE
        self.last_extended_event = None

    def push_controller(self, controller):
        self.controllers.append(controller)

    def pop_controller(self):
        self.controllers.pop()

class CallHandle(CallHandleBase):
    """An Aculab call handle, and common operations on it.

    Some events are handled to maintain the internal state, but in general,
    event handling is delegated to the controller."""

    def __init__(self, controller, user_data = None, card = 0, port = 0,
                 timeslot = None, reactor = CallReactor):

        CallHandleBase.__init__(self, controller, user_data, port, reactor)
        
        # automatically translate port numbers to v6 port_ids
        if lowlevel.cc_version >= 6:
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
            
        self.details = lowlevel.DETAIL_XPARMS()

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
        self.name = 'Cch-%04x' % self.handle

        self.reactor.add(self)

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
        self.name = 'Cch-%04x' % self.handle

        self.reactor.add(self)

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
        self.name = 'Cch-%04x' % self.handle

        self.reactor.add(self)

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
           Returns a NetEndpoint.
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

        return NetEndpoint(self.switch, self.port, (self.details.stream,
                                                    self.details.ts))

    def speak_to(self, sink):
        """source is a tuple of (stream, timeslot).
           Returns a CTBusEndpoint.
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

        return CTBusEndpoint(self.switch, sink)

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
        """Disconnect a call. Cause may be a CAUSE_XPARMS struct or an int"""
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
        """Release a call. Cause may be a CAUSE_XPARMS struct or an int"""

        self.reactor.remove(self)

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
            self.name = 'Cch-%04x' % self.handle
            del self.in_handle
        else:
            self.handle = None
            self.name = 'Cch-0000'
            
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
        # Assert idle pattern according to Q.522, section 2.12
        rc = lowlevel.idle_net_ts(self.port, self.details.ts)
        if rc:
            raise AculabError(rc, 'idle_net_ts', self.handle)
        self.release()

class Call(CallHandle):
    """A Call is a CallHandle that does an automatic openin upon creation."""

    def __init__(self, controller, user_data = None, card = 0, port = 0,
                 timeslot = -1, reactor = CallReactor):
        
        CallHandle.__init__(self, controller, user_data,
                            card, port, timeslot, reactor)

        self.openin()

            

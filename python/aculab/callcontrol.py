"""Call Control - a thin layer on top of the Aculab API.

Terminology: what is called a 'call' in this module should be called a
'call leg' according to international treaties, but in Aculab's nomenclature,
it's a call, so we stick with that.
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
    """Base class for Call Handles.

    Holds common members and the controller stack."""

    def __init__(self, controller, user_data = None, port = 0,
                 reactor = CallReactor):

        self.user_data = user_data
        # this is a stack of controllers
        self.controllers = [controller]
        self.reactor = reactor
        self.port = port

        self.handle = None
        self.name = 'cc-0000'
        
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

    All events are delegated to the controller; some events are handled
    internally to maintain the state."""

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

    def openin(self, unique=None, cnf=None):
        """Open a call handle for incoming calls.

        @param unique: see U{unique_xparms
        <http://www.aculab.com/Support/v6_api/CallControl/cc8.htm>}.
        @param cnf: see U{cnf
        <http://www.aculab.com/Support/v6_api/CallControl/glos/cnf.htm>}
        """
        inparms = lowlevel.IN_XPARMS()
        inparms.net = self.port
        inparms.ts = self.timeslot
        if cnf:
            inparms.cnf = cnf
        else:
            inparms.cnf = lowlevel.CNF_REM_DISC
            if self.timeslot != -1:
                inparms.cnf |= lowlevel.CNF_TSPREFER
                
        if unique:
            inparms.unique_xparms = unique

        rc = lowlevel.call_openin(inparms)
        if rc:
            raise AculabError(rc, 'call_openin')

        self.handle = inparms.handle
        self.name = 'cc-%04x' % self.handle

        self.reactor.add(self)

        log.debug('%s openin()', self.name)

    def _outparms(self, destination_address, sending_complete = True,
                  originating_address = '', unique = None,
                  feature_type = None, feature = None, cnf = None):
        """Used internally."""
        
        if feature_type and feature:
            outparms = lowlevel.FEATURE_OUT_XPARMS()

            if cnf:
                outparms.cnf = cnf
            else:
                outparms.cnf = lowlevel.CNF_REM_DISC
                if self.timeslot != -1:
                    outparms.cnf |= lowlevel.CNF_TSPREFER

            outparms.feature_information = feature_type
            outparms.feature = feature
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
                feature_type = None, feature = None, cnf = None):
        """Make an outgoing call.

        @param destination_address: number to dial.
        @param sending_complete: Typically C{True}, unless overlap sending is
        used. See L{send_overlap}.
        @param originating_address: often also called the CLI.
        @param unique: see U{unique_xparms
        <http://www.aculab.com/Support/v6_api/CallControl/cc8.htm>}.
        @param feature_type: see U{feature_information
        <http://www.aculab.com/Support/v6_api/CallControl/glos/\
        feature_information2.htm>}.
        @param feature: see U{feature_union
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_feature_openout.htm>}.
        @param cnf: see U{cnf
        <http://www.aculab.com/Support/v6_api/CallControl/glos/cnf.htm>}.
        """
        
        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, unique,
                                  feature_type, feature, cnf)
        
        if feature_type and feature:
            rc = lowlevel.call_feature_openout(outparms)
            if rc:
                raise AculabError(rc, 'call_feature_openout')
        else:
            rc = lowlevel.call_openout(outparms)
            if rc:
                raise AculabError(rc, 'call_openout')

        # it is permissible to do an openout after an openin.
        # we save the handle from openin in this case
        if self.handle:
            self.in_handle = self.handle

        self.handle = outparms.handle
        self.name = 'cc-%04x' % self.handle

        self.reactor.add(self)

        log.debug('%s openout(%s, %d, %s)', self.name, destination_address,
                  sending_complete, originating_address)

    def feature_send(self, feature_type, feature,
                     message_control=lowlevel.CONTROL_NEXT_CC_MESSAGE):
        """Send feature information at different stages during the lifetime of
        a call.

        @param feature_type: see U{feature_information
        <http://www.aculab.com/Support/v6_api/CallControl/glos/\
        feature_information2.htm>}.
        @param feature: see U{feature_union
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_feature_openout.htm>}.
        @param message_control: see U{message_control
        <http://www.aculab.com/Support/v6_api/CallControl/glos/\
        message_control.htm>}.
        Default is C{CONTROL_NEXT_CC_MESSAGE}.
        
        See also: U{call_feature_send
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_feature_send.htm>}.
        """
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

    def enquiry(self, destination_address, sending_complete=1,
                originating_address='', unique=None,
                feature_type=None, feature=None, cnf=None):
        """Make an I{enquiry} call, i.e. a call to a third party while
        another call is on hold.

        @param destination_address: number to dial.
        @param sending_complete: Typically C{True}, unless overlap sending is
        used. See L{send_overlap}.
        @param originating_address: often also called the CLI.
        @param unique: see U{unique_xparms
        <http://www.aculab.com/Support/v6_api/CallControl/cc8.htm>}.
        @param feature_type: see U{feature_information
        <http://www.aculab.com/Support/v6_api/CallControl/glos/\
        feature_information2.htm>}.
        @param feature: see U{feature_union
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_feature_openout.htm>}.
        @param cnf: see U{cnf
        <http://www.aculab.com/Support/v6_api/CallControl/glos/cnf.htm>}
        """
        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, unique, feature_type,
                                  feature, cnf)

        if feature_type and feature:
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
        self.name = 'cc-%04x' % self.handle

        self.reactor.add(self)

        log.debug('%s enquiry(%s, %d, %s)', self.name, destination_address,
                  sending_complete, originating_address)

    def transfer(self, call):
        """Transfer to another call.
        
        This call must be on hold and other call must have been initiated
        with L{tenquiry}.

        @param call: The call to transfer to.

        See U{call_transfer
        <http://www.aculab.com/Support/v6_api/CallControl/call_transfer.htm>}.
        """
        transfer = lowlevel.TRANSFER_XPARMS()
        transfer.handlea = self.handle
        transfer.handlec = call.handle
        
        rc = lowlevel.call_transfer(transfer)
        if rc:
            raise AculabError(rc, 'call_transfer', self.handle)
        
        log.debug('%s transfer(%s)', self.name, call.name)

    def hold(self):
        """Put a call on hold.
        
        See U{call_hold
        <http://www.aculab.com/Support/v6_api/CallControl/call_hold.htm>}.
        """
        rc = lowlevel.call_hold(self.handle)
        if rc:
            raise AculabError(rc, 'call_hold', self.handle)

        log.debug('%s hold()', self.name)

    def reconnect(self):
        """Retrieve a call that was previously put on hold.
        
        See U{call_reconnect
        <http://www.aculab.com/Support/v6_api/CallControl/call_reconnect.htm>}.
        """
        rc = lowlevel.call_reconnect(self.handle)
        if rc:
            raise AculabError(rc, 'call_reconnect', self.handle)

        log.debug('%s reconnect()', self.name)

    def send_overlap(self, addr, complete = False):
        """Send overlap digits.

        @param sending_complete: Set this to C{True} if you know that the
        number is complete. This is of limited use: if you know the entire
        number, you don't need overlap sending, and if you use overlap sending,
        you typically don't know when the number is complete.
        @param addr: I don't remember whether this should be the entire number
        so far or incremental digits. Aculab's tech writers don't know either.

        See U{call_send_overlap <http://www.aculab.com/Support/v6_api/\
        CallControl/call_send_overlap.htm>}.
        """
        overlap = lowlevel.OVERLAP_XPARMS()
        overlap.handle = self.handle
        overlap.sending_complete = complete
        overlap.destination_addr = addr

        rc = lowlevel.call_send_overlap(overlap)
        if rc:
            raise AculabError(rc, 'call_send_overlap', self.handle)

        log.debug('%s send_overlap(%s, %d)', self.name, addr, complete)

    def send_keypad_info(self, keypad = '', display = ''):
        """Untested/undocumented.

        See U{call_send_keypad_info
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_send_keypad_info.htm>}.
        """
        keypadx = lowlevel.KEYPAD_XPARMS()
        keypadx.handle = self.handle
        keypadx.unique_xparms.sig_q931.location = lowlevel.KEYPAD_CONNECT
        keypadx.unique_xparms.sig_q931.keypad.setie(keypad)
        keypadx.unique_xparms.sig_q931.display.setie(display)

        rc = lowlevel.call_send_keypad_info(keypadx)
        if rc:
            raise AculabError(rc, 'call_send_keypad_info')

    def listen_to(self, source):
        """Listen to a timeslot on a L{CTbus}.
        
        @param source: a tuple of (stream, timeslot).
        @returns a NetEndpoint.
        
        B{Note:} Do not ignore the return value - it will dissolve
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
        """Talk to a timeslot on a L{CTBus}.
        
        @param source: a tuple of (stream, timeslot).
        @returns a L{CTBusEndpoint}.
        
        B{Note:} Do not ignore the return value - it will dissolve
        the connection when it is garbage collected"""

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
        """Return the cause for a disconnected or failed call.

        @returns: a C{CAUSE_XPARMS} structure.

        See U{call_getcause
        <http://www.aculab.com/Support/v6_api/CallControl/call_getcause.htm>}.
        """
        cause = lowlevel.CAUSE_XPARMS()
        cause.handle = self.handle
        rc = lowlevel.call_getcause(cause)
        if rc:
            raise AculabError(rc, 'call_details', self.handle)

        return cause
    
    def get_details(self):
        """Return (and cache) the details of a call.

        @returns: a C{DETAIL_XPARMS} structure.

        See U{call_details
        <http://www.aculab.com/Support/v6_api/CallControl/call_details.htm>}.
        """
        self.details = lowlevel.DETAIL_XPARMS()
        self.details.handle = self.handle

        rc = lowlevel.call_details(self.details)
        if rc:
            raise AculabError(rc, 'call_details', self.handle)

        return self.details

    def get_feature_details(self, type):
        """Return (and cache) the feature details of a call.

        See U{call_feature_details
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_feature_details.htm>}.

        @returns: a C{FEATURE_DETAIL_XPARMS} structure.
        """
        self.feature_details = lowlevel.FEATURE_DETAIL_XPARMS()
        self.feature_details.handle = self.handle
        self.feature_details.feature_type = type

        rc = lowlevel.call_feature_details(self.feature_details)
        if rc:
            raise AculabError(rc, 'call_feature_details', self.handle)

        return self.feature_details

    def accept(self):
        """Accept the incoming call.
        
        See U{call_accept
        <http://www.aculab.com/Support/v6_api/CallControl/call_accept.htm>}.
        """
        rc = lowlevel.call_accept(self.handle)
        if rc:
            raise AculabError(rc, 'call_accept', self.handle)

        log.debug('%s accept()', self.name)

    def incoming_ringing(self):
        """Signal incoming ringing to the far end.
        
        See U{call_incoming_ringing
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_incoming_ringing.htm>}.
        """
        rc = lowlevel.call_incoming_ringing(self.handle)
        if rc:
            raise AculabError(rc, 'call_incoming_ringing', self.handle)

        log.debug('%s incoming_ringing()', self.name)

    def disconnect(self, cause = None):
        """Disconnect a call.
        @param cause: this may be a C{CAUSE_XPARMS} struct or an
        int for an Aculab cause value.
        
        See U{call_disconnect
        <http://www.aculab.com/Support/v6_api/CallControl/\
        call_disconnect.htm>}.
        """
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
        """Release the call.
        
        @param cause: this may be a C{CAUSE_XPARMS} struct or an
        int for an Aculab cause value.
        
        See U{call_release
        <http://www.aculab.com/Support/v6_api/CallControl/call_release.htm>}.
        """

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
            self.name = 'cc-%04x' % self.handle
            del self.in_handle
        else:
            self.handle = None
            self.name = 'cc-0000'
            
    def ev_incoming_call_det(self):
        """Internal event handler for C{EV_INCOMING_CALL_DETECTED}.

        Calls L{get_details} to cache them.
        """
        self.get_details()

    def ev_ext_hold_request(self):
        """Internal event handler for C{EV_EXT_HOLD_REQUEST}.

        Calls L{get_details} to update the details.
        """
        self.get_details()

    def ev_outgoing_ringing(self):
        """Internal event handler for C{EV_OUTGOING_RINGING}.

        Calls L{get_details} to cache them.
        """
        self.get_details()

    def ev_call_connected(self):
        """Internal event handler for C{EV_CALL_CONNECTED}.

        Calls L{get_details} to update the details.
        """        
        self.get_details()

    def ev_idle(self):
        """Internal event handler for C{EV_EXT_HOLD_REQUEST}.

        This method calls:
         - L{get_details} to update the details
         - U{idle_net_ts
         <http://www.aculab.com/Support/v6_api/CallControl/idle_net_ts.htm>}
         to assert a suitable idle pattern (for ISDN, see Q.522, section 2.12).
        """        
        self.get_feature_details(lowlevel.FEATURE_FACILITY)
        self.get_details()
        # Assert idle pattern according to Q.522, section 2.12
        rc = lowlevel.idle_net_ts(self.port, self.details.ts)
        if rc:
            raise AculabError(rc, 'idle_net_ts', self.handle)
        self.release()

class Call(CallHandle):
    """A Call is a CallHandle that does an automatic L{openin} upon
    creation."""

    def __init__(self, controller, user_data = None, card = 0, port = 0,
                 timeslot = -1, reactor = CallReactor):
        """Create a L{CallHandle} and open it for incoming calls.
        """
        
        CallHandle.__init__(self, controller, user_data,
                            card, port, timeslot, reactor)

        self.openin()

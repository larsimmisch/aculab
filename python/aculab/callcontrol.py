import sys
import getopt
import lowlevel
from busses import CTBusConnection
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

class CallEventDispatcher:

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
        
        while 1:
            if not self.calls:
                return
            
            event.handle = 0
            event.timeout = 1000

            rc = lowlevel.call_event(event)
            if rc:
                raise AculabError(rc, 'call_event')

            handled = ''
            
            # call the event handlers
            if event.handle:
                call = self.calls[event.handle]
                if event.state == lowlevel.EV_EXTENDED:
                    ev = ext_event_names[event.extended_state].lower()
                else:
                    ev = event_names[event.state].lower()
                    
                if hasattr(call.controller, 'mutex'):
                    mutex = call.controller.mutex
                    mutex.acquire()
                else:
                    mutex = None

                try:
                    # let the call handle events first
                    try:
                        m = getattr(call, ev)
                        m()
                        handled = '(call'
                    except AttributeError:
                        if hasattr(call, ev):
                            raise
                    except:
                        raise

                    # pass the event on to the controller
                    try:
                        m = getattr(call.controller, ev)
                        m(call)
                        if handled:
                            handled += ', controller)'
                        else:
                            handled = '(controller)'
                    except AttributeError:
                        if handled:
                            handled += ')'
                        if hasattr(call.controller, ev):
                            raise
                    except:
                        raise

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

                if self.verbose:
                    if not handled:
                        handled = '(ignored)'
                    print hex(event.handle), ev, handled


# The CallHandle class models a call handle, as defined by the Aculab lowlevel,
# and common operations on it. Some events are handled to maintain the 
# internal state, but in general, event handling is delegated to the
# controller.

class CallHandle:

    def __init__(self, controller, dispatcher, user_data = None, port = 0,
                 timeslot = None):

        self.user_data = user_data
        self.controller = controller
        self.dispatcher = dispatcher
        self.port = port
        if not timeslot:
            self.timeslot = -1
        else:
            self.timeslot = timeslot
        self.handle = None
        self.details = lowlevel.DETAIL_XPARMS()
        # The dispatcher sets the last state changing event after dispatching
        # the event. Which events are deemed state changing is controlled via
        # no_state_change_events
        self.last_event = lowlevel.EV_IDLE
        self.last_extended_event = None

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

        # print '0x%x' % self.handle

        self.dispatcher.add(self)

    def _outparms(self, destination_address, sending_complete = 1,
                  originating_address = '',
                  feature = None, feature_data = None, cnf = None):
        
        if feature and feature_data:
            outparms = lowlevel.FEATURE_OUT_XPARMS()
            outparms.net = self.port
            outparms.ts = self.timeslot

            if cnf:
                outparms.cnf = cnf
            else:
                outparms.cnf = lowlevel.CNF_REM_DISC
                if self.timeslot != -1:
                    outparms.cnf |= lowlevel.CNF_TSPREFER
                
            outparms.sending_complete = sending_complete
            outparms.originating_addr = originating_address
            outparms.destination_addr = destination_address
            outparms.feature_information = feature
            outparms.feature = feature_data
        else:
            outparms = lowlevel.OUT_XPARMS()
            outparms.net = self.port
            outparms.ts = self.timeslot
            outparms.cnf = lowlevel.CNF_REM_DISC
            if self.timeslot != -1:
                outparms.cnf |= lowlevel.CNF_TSPREFER
                
            outparms.sending_complete = sending_complete
            outparms.originating_addr = originating_address
            outparms.destination_addr = destination_address

        return outparms

    def openout(self, destination_address, sending_complete = 1,
                originating_address = '',
                feature = None, feature_data = None, cnf = None):

        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, feature, feature_data,
                                  cnf)
        
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
        if self.handle and (self.handle & lowlevel.INCH):
            self.in_handle = self.handle

        self.handle = outparms.handle

        self.dispatcher.add(self)

    def enquiry(self, destination_address, sending_complete = 1,
                originating_address = '',
                feature = None, feature_data = None, cnf = None):

        outparms = self._outparms(destination_address, sending_complete,
                                  originating_address, feature, feature_data,
                                  cnf)

        if feature and feature_data:
            rc = lowlevel.call_feature_enquiry(outparms)
            if rc:
                raise AculabError(rc, 'call_feature_enquiry')
        else:
            rc = lowlevel.call_enquiry(outparms)
            if rc:
                raise AculabError(rc, 'call_enquiry')

        # it is permissible to do an openout after an openin
        # we save the handle from openin in this case
        if self.handle and (self.handle & lowlevel.INCH):
            self.in_handle = self.handle

        self.handle = outparms.handle

        self.dispatcher.add(self)

    def hold(self):
        rc = lowlevel.call_hold(self.handle)
        if rc:
            raise AculabError(rc, 'call_hold')

    def reconnect(self):
        rc = lowlevel.call_reconnect(self.handle)
        if rc:
            raise AculabError(rc, 'call_reconnect')

    def send_overlap(self, addr, complete = 0):
        overlap = lowlevel.OVERLAP_XPARMS()
        overlap.handle = self.handle
        overlap.sending_complete = complete
        overlap.destination_addr = addr

        rc = lowlevel.call_send_overlap(overlap)
        if rc:
            raise AculabError(rc, 'call_send_overlap')

    def listen_to(self, source):
        """source is a tuple of (stream, timeslot).
           Returns a CTBusConnection.
           Do not discard the return value - it will dissolve
           the connection when it's garbage collected"""

        output = lowlevel.OUTPUT_PARMS()
        output.ost = self.details.stream
        output.ots = self.details.ts
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        sw = lowlevel.call_port_2_swdrvr(self.port)

        rc = lowlevel.sw_set_output(sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        return CTBusConnection(sw, (self.details.stream, self.details.ts))

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

        sw = lowlevel.call_port_2_swdrvr(self.port)

        rc = lowlevel.sw_set_output(sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        return CTBusConnection(sw, sink)

    def get_cause(self):
        cause = lowlevel.CAUSE_XPARMS()
        cause.handle = self.handle
        rc = lowlevel.call_getcause(cause)
        if rc:
            raise AculabError(rc, 'call_details')

        return cause
    
    def get_details(self):
        self.details = lowlevel.DETAIL_XPARMS()
        self.details.handle = self.handle

        rc = lowlevel.call_details(self.details)
        if rc:
            raise AculabError(rc, 'call_details')

        return self.details

    def get_feature_details(self, type):
        self.feature_details = lowlevel.FEATURE_DETAIL_XPARMS()
        self.feature_details.handle = self.handle
        self.feature_details.feature_type = type

        rc = lowlevel.call_feature_details(self.feature_details)
        if rc:
            raise AculabError(rc, 'call_feature_details')

        return self.feature_details

    def accept(self):
        rc = lowlevel.call_accept(self.handle)
        if rc:
            raise AculabError(rc, 'call_accept')

    def incoming_ringing(self):
        rc = lowlevel.call_incoming_ringing(self.handle)
        if rc:
            raise AculabError(rc, 'call_incoming_ringing')

    def disconnect(self, cause = None):
        '''cause may be a CAUSE_XPARMS struct or an int'''
        if self.handle:
            if cause is None:
                xcause = lowlevel.CAUSE_XPARMS()
            elif type(cause) == type(0):
                xcause = lowlevel.CAUSE_XPARMS()
                xcause.cause = cause
            else:
                xcause = cause

            xcause.handle = self.handle
            
            rc = lowlevel.call_disconnect(xcause)
            if rc:
                raise AculabError(rc, 'call_disconnect')

    def release(self, cause = None):
        '''cause may be a CAUSE_XPARMS struct or an int'''

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
                raise AculabError(rc, 'call_release')

        # restore the handle for the inbound call if there is one
        if hasattr(self, 'in_handle'):
            self.handle = self.in_handle
            del self.in_handle
        else:
            self.handle = None
            
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

    def __init__(self, controller, dispatcher, user_data = None, port = 0,
                 timeslot = -1):
        
        CallHandle.__init__(self, controller, dispatcher, user_data,
                            port, timeslot)

        self.openin()

            

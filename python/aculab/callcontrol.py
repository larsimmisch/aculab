import sys
import getopt
import lowlevel
from error import AculabError
from names import event_names

class CallEventDispatcher:

    def __init__(self):
        self.calls = {}

    # must only be called from a dispatched event
    # - not from a separate thread
    def add(self, call):
        self.calls[call.handle] = call

    # must only be called from a dispatched event
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
                ev = event_names[event.state].lower()
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
                
                if not handled:
                    handled = '(ignored)'

                print hex(event.handle), ev, handled


dispatcher = CallEventDispatcher()

# The CallHandle class models a call handle, as defined by the Aculab lowlevel,
# and common operations on it. Event handling is delegated to the controller,
# in classical OO decomposition.

class Call:

    def __init__(self, controller, port = 0, number = '', timeslot = -1):
        self.controller = controller
        self.port = port
        if number:
            self.number = number
        self.timeslot = timeslot

        self.restart()

    def restart(self):
        if hasattr(self, 'number'):
            self.openout()
        else:
            self.openin()
            
    def openin(self):
        inparms = lowlevel.IN_XPARMS()
        inparms.net = self.port
        inparms.ts = self.timeslot
        inparms.cnf = lowlevel.CNF_REM_DISC | lowlevel.CNF_TSPREFER

        rc = lowlevel.call_openin(inparms)
        if rc:
            raise AculabError(rc, 'call_openin')

        self.handle = inparms.handle

        dispatcher.add(self)

    def openout(self):
        outparms = lowlevel.OUT_XPARMS()
        outparms.net = self.port
        outparms.ts = self.timeslot
        outparms.cnf = lowlevel.CNF_REM_DISC | lowlevel.CNF_TSPREFER
        outparms.sending_complete = 1
        outparms.originating_address = '3172542'
        outparms.destination_address = self.number

        rc = lowlevel.call_openout(outparms)
        if rc:
            raise AculabError(rc, 'call_openout')

        self.handle = outparms.handle

        dispatcher.add(self)

    def send_overlap(self, addr, complete = 0):
        overlap = lowlevel.OVERLAP_XPARMS()
        overlap.handle = self.handle
        overlap.sending_complete = complete
        overlap.destination_addr = addr

        rc = lowlevel.call_send_overlap(overlap)
        if rc:
            raise AculabError(rc, 'call_send_overlap')

    def listen_to(self, sink, source):
        """sink and source are tuples of timeslots.
           returns the tuple (switch, sink)."""
        output = lowlevel.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        sw = lowlevel.call_port_2_swdrvr(self.port)

        print "%d: %d:%d := %d:%d" % (sw, sink[0], sink[1],
                                      source[0], source[1])
        
        rc = lowlevel.sw_set_output(sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

        return (sw, sink)
    
    def disable(self, source):
        output = lowlevel.OUTPUT_PARMS()
        output.ost = source[0]
        output.ots = source[1]
        output.mode = lowlevel.DISABLE_MODE

        sw = lowlevel.call_port_2_swdrvr(self.port)

        rc = lowlevel.sw_set_output(sw, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')        

    def get_details(self):
        self.details = lowlevel.DETAIL_XPARMS()
        self.details.handle = self.handle

        rc = lowlevel.call_details(self.details)
        if rc:
            raise AculabError(rc, 'call_details')

        return self.details

    def accept(self):
        rc = lowlevel.call_accept(self.handle)
        if rc:
            raise AculabError(rc, 'call_accept')

    def incoming_ringing(self):
        rc = lowlevel.call_incoming_ringing(self.handle)
        if rc:
            raise AculabError(rc, 'call_incoming_ringing')

    def disconnect(self, cause = 0):
        if self.handle:
            causeparms = lowlevel.CAUSE_XPARMS()
            causeparms.handle = self.handle
            causeparms.cause = cause
            rc = lowlevel.call_disconnect(causeparms)
            if rc:
                raise AculabError(rc, 'call_disconnect')
            
    def ev_incoming_call_det(self):
        self.get_details()

    def ev_ext_hold_request(self):
        self.get_details()

    def ev_outgoing_ringing(self):
        self.get_details()

    def ev_call_connected(self):
        self.get_details()

    def ev_idle(self):
        dispatcher.remove(self)
        cause = lowlevel.CAUSE_XPARMS()
        cause.handle = self.handle

        self.handle = None

        if hasattr(self, 'details'):
            del self.details

        if hasattr(self, 'number'):
            del self.number

        rc = lowlevel.call_release(cause)
        if rc:
            raise AculabError(rc, 'call_release')
        

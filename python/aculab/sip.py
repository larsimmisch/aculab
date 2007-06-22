"""SIP calls.
"""
import sys
import getopt
import lowlevel
import logging
from busses import Connection, CTBusEndpoint, NetEndpoint, DefaultBus
from error import AculabError
from names import event_names
from callcontrol import CallHandleBase, CallDispatcher
from snapshot import Snapshot

log = logging.getLogger('sip')

class SIPHandle(CallHandleBase):
    """An Aculab SIP call handle, and common operations on it.

    Some events are handled to maintain the internal state, but in general,
    event handling is delegated to the controller."""

    def __init__(self, controller, user_data = None,
                 dispatcher = CallDispatcher):

        sip_port = Snapshot().sip
        if sip_port is None:
            raise RuntimeError('no SIP service running')

        CallHandleBase.__init__(self, controller, user_data, sip_port,
                                dispatcher)
        
    def openin(self, request_notification_mask = 0,
               response_notification_mask = 0, call_options = 0):
        
        inparms = lowlevel.SIP_IN_XPARMS()
        inparms.net = self.port
        inparms.request_notification_mask = request_notification_mask
        inparms.response_notification_mask = response_notification_mask
        inparms.call_options = call_options
        
        rc = lowlevel.sip_openin(inparms)
        if rc:
            raise AculabError(rc, 'sip_openin')

        self.handle = inparms.handle
        self.name = hex(self.handle)

        self.dispatcher.add(self)

        log.debug('%s openin()', self.name)

    def openout(self, destination_address, sdp, originating_address = '',
                contact_address = None, request_notification_mask = 0,
                response_notification_mask = 0, call_options = 0,
                custom_headers = None):

        media = ACU_MEDIA_OFFER_ANSWER()
        media.raw_sdp = str(sdp)
        
        outparms = lowlevel.SIP_OUT_PARMS()
        outparms.destination_addr = destination_address
        outparms.originating_addr = originating_address
        outparms.contact_addr = contact_address
        outparms.request_notification_mask = request_notification_mask
        outparms.response_notification_mask = response_notification_mask
        outparms.call_options = call_options
        outparms.media_offer_answer = media
        
        # it is permissible to do an openout after an openin
        # we save the handle from openin in this case
        if self.handle:
            self.in_handle = self.handle

        rc = lowlevel.sip_openout(outparms)
        if rc:
            raise AculabError(rc, 'sip_openout')

        self.handle = outparms.handle
        self.name = hex(self.handle)

        self.dispatcher.add(self)

        log.debug('%s openout(%s, %s)', self.name, destination_address,
                  originating_address)

    def get_details(self):
        if self.details:
            sip_free_details(self.details)
            
        self.details = lowlevel.SIP_DETAIL_PARMS()
        self.details.handle = self.handle

        rc = lowlevel.sip_details(self.details)
        if rc:
            raise AculabError(rc, 'call_details', self.handle)

        return self.details

    def accept(self, sdp, contact_address = None):
        """Accept the call."""

        media = ACU_MEDIA_OFFER_ANSWER()
        media.raw_sdp = str(sdp)
        
        accept = lowlevel.SIP_ACCEPT_PARMS()
        accept.handle = self.handle
        accept.media_offer_answer = media
        
        rc = lowlevel.sip_accept(accept)
        if rc:
            raise AculabError(rc, 'sip_accept', self.handle)

        log.debug('%s accept()', self.name)

    def incoming_ringing(self):
        """Signal incoming ringing."""
        ringing = lowlevel.SIP_INCOMING_RINGING_PARMS()
        ringing.handle = self.handle
        
        rc = lowlevel.call_incoming_ringing(ringing)
        if rc:
            raise AculabError(rc, 'sip_incoming_ringing', self.handle)

        log.debug('%s incoming_ringing()', self.name)

        return ringing

    def disconnect(self, code = 200):
        """Disconnect a call. Cause may be a CAUSE_XPARMS struct or an int"""
        disconnect = lowlevel.SIP_DISCONNECT_PARMS()
        disconnect.sip_code = code

        if self.handle:
            disconnect.handle = self.handle

            rc = lowlevel.sip_disconnect(disconnect)
            if rc:
                raise AculabError(rc, 'sip_disconnect', self.handle)

        log.debug('%s disconnect(%d)', self.name, code)

    def release(self):
        """Release a call."""

        if self.details:
            sip_free_details(self.details)
            self.details = None
        
        self.dispatcher.remove(self)

        if self.handle:
            disconnect = lowlevel.DISCONNECT_XPARMS()
            disconnect.handle = self.handle
            
            rc = lowlevel.xcall_release(disconnect)
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
        self.release()

class SIPCall(SIPHandle):
    """A SIPCall is a SIPCallHandle that does an automatic openin upon
    creation."""

    def __init__(self, controller, user_data = None,
                 dispatcher = CallDispatcher):
        
        SIPHandle.__init__(self, controller, user_data, dispatcher)

        self.openin()

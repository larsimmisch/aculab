# Copyright (C) 2005-2007 Lars Immisch

"""A snapshot of all available cards, ports and modules (v6 API and later)."""

from pprint import PrettyPrinter
import lowlevel
from error import AculabError

_singletons = {}

class Card(object):
    """Base class for an Aculab card.

    The member C{card} has the type U{ACU_OPEN_CARD_PARMS
    http://www.aculab.com/Support/v6_api/Resources/acu_open_card.htm}.

    The member C{info} has the type U{ACU_CARD_INFO_PARMS
    http://www.aculab.com/Support/v6_api/Resources/acu_get_card_info.htm}.

    Prosody X cards have a member C{ip_address} that is not C{None}.
    """
    
    def __init__(self, card, info):
        self.card_id = card.card_id
        self.card = card
        self.info = info
        self.ip_address = None

class SwitchCard(Card):
    """An Aculab card with a switch matrix.

    Cards typically have other functions than just switching, but all cards
    that support switching will also represented by an instance of this class.

    The member C{open} has the type U{ACU_OPEN_SWITCH_PARMS
    http://www.aculab.com/support/v6_api/Resources/acu_open_switch.htm}.
    """
    def __init__(self, card, info):
        Card.__init__(self, card, info)
        
        switchp = lowlevel.ACU_OPEN_SWITCH_PARMS()
        switchp.card_id = card.card_id
        rc = lowlevel.acu_open_switch(switchp)
        if rc:
            raise AculabError(rc, 'acu_open_switch')

        self.open = switchp

    def __repr__(self):
        return 'SwitchCard(%s)' % self.card.serial_no

class Port(object):
    """A port on an Aculab call control card.

    The member C{open} has the type U{OPEN_PORT_PARMS
    http://www.aculab.com/support/v6_api/callcontrol/call_open_port.htm}.
    """
    def __init__(self, card, index):
        self.index = index
        open_portp = lowlevel.OPEN_PORT_PARMS()

        open_portp.card_id = card.card_id
        open_portp.port_ix = index

        rc = lowlevel.call_open_port(open_portp)
        if rc:
            raise AculabError(rc, 'call_open_port')

        info_portp = lowlevel.PORT_INFO_PARMS()
        info_portp.port_id = open_portp.port_id

        rc = lowlevel.call_port_info(info_portp)
        if rc:
            raise AculabError(rc, 'call_port_info')

        self.open = open_portp
        self.info = info_portp

    def __repr__(self):
        return 'Port(%d)' % self.index

class CallControlCard(Card):
    """An Aculab card capable of call control.

       The member C{open} has the type U{ACU_OPEN_CALL_PARMS
       http://www.aculab.com/support/v6_api/Resources/acu_open_call.htm}.

       The member C{info} has the type U{CARD_INFO_PARMS
       http://www.aculab.com/Support/v6_api/CallControl/\
       call_get_card_info.htm}.
       """
    def __init__(self, card, info):
        Card.__init__(self, card, info)

        callp = lowlevel.ACU_OPEN_CALL_PARMS()
        callp.card_id = card.card_id
        rc = lowlevel.acu_open_call(callp)
        if rc:
            raise AculabError(rc, 'acu_open_call')

        infop = lowlevel.CARD_INFO_PARMS()
        infop.card_id = card.card_id
        rc = lowlevel.call_get_card_info(infop)
        if rc:
            raise AculabError(rc, 'call_get_card_info')

        self.info = infop

        if infop.card_type == lowlevel.ACU_PROSODY_X_CARD:
            ipinfo = lowlevel.ACU_PROSODY_IP_CARD_REGISTRATION_PARMS()
            
            ipinfo.card = self.card.serial_no
            
            rc = lowlevel.acu_get_prosody_ip_card_config(ipinfo)
            if rc:
                raise AculabError(rc, '%s acu_get_prosody_ip_card_config' \
                                  % self.card.serial_no)

            self.ip_address = ipinfo.ip4_address;

        self.ports = [Port(card, i) for i in range(infop.ports)]

    def __repr__(self):
        if self.ip_address:
            return 'CallControlCard(%s, %s)' \
                   % (self.card.serial_no, self.ip_address)
        else:
            return 'CallControlCard(%s)' % self.card.serial_no
            
class Module(object):
    """A DSP module on an Aculab Prosody (speech processing) card.

    The member C{open} has the type U{SM_OPEN_MODULE_PARMS
    http://www.aculab.com/support/TiNG/gen/apifn-sm_open_module.html}.    

    The member C{info} has the type U{SM_MODULE_INFO_PARMS
    http://www.aculab.com/support/TiNG/gen/apifn-sm_get_module_info.html}.    
    """

    # Tone matrix for combined DTMF/FAX toneset
    dtmf_fax_tonematrix = (( '1', '2', '3', None ),
                           ( '4', '5', '6', None ),
                           ( '7', '8', '9', None ),
                           ( '*', '0', '#', None ),
                           ( None, None, None, 'CNG' ),
                           ( None, None, None, 'CED' ))
    
    def __init__(self, card, index):
        self.open = lowlevel.SM_OPEN_MODULE_PARMS()

        self.open.card_id = card.card_id
        self.open.module_ix = index
        rc = lowlevel.sm_open_module(self.open)
        if rc:
            raise AculabError(rc, 'sm_open_module')

        self.info = lowlevel.SM_MODULE_INFO_PARMS()
        self.info.module = self.open.module_id
        rc = lowlevel.sm_get_module_info(self.info)
        if rc:
            raise AculabError(rc, 'sm_get_module_info')

        from switching import ProsodyTimeslots

        self.vmptx_toneset_id = None
        self.dtmf_fax_toneset_id = None
        self.timeslots = ProsodyTimeslots(self.info.min_stream)

    def add_tone_limits(self, lower, upper):
        """Helper function for L{dtmf_fax_toneset}."""

        coeff = lowlevel.SM_INPUT_FREQ_COEFFS_PARMS()

        coeff.module = self.info.module
        coeff.lower_limit = lower
        coeff.upper_limit = upper

        rc = lowlevel.sm_add_input_freq_coeffs(coeff)
        if rc:
            raise AculabError(rc, 'sm_add_input_freq_coeffs')        

        return coeff.id

    def dtmf_fax_toneset(self):
        """Create a custom toneset for the detection of DTMF and CED/CNG at
        the same time. This toneset is cached; upon the first invocation, the
        toneset will be created on the module, further invocations just return
        the existing identifier."""

        if self.dtmf_fax_toneset_id is not None:
            return self.dtmf_fax_toneset_id

        # The first group of frequencies
        toneid = self.add_tone_limits(679.6875, 710.9375)
        self.add_tone_limits(742.1875, 789.0625)
        self.add_tone_limits(835.9375, 867.1875)
        self.add_tone_limits(914.0625, 960.9375)
        self.add_tone_limits(1062.0, 1138.0)     # CNG +/- 10% 
        self.add_tone_limits(2085.0, 2115.0)     # CED +/- 10% 

        # The second group of frequencies
        self.add_tone_limits(1179.6875, 1242.1875)
        self.add_tone_limits(1304.6875, 1367.1875)
        self.add_tone_limits(1445.3125, 1507.8125)
        self.add_tone_limits(0, 0)

        toneset = lowlevel.SM_INPUT_TONE_SET_PARMS()

        toneset.module = self.info.module
        toneset.band1_first_freq_coeffs_id = toneid
        toneset.band1_freq_count = 6
        toneset.band2_first_freq_coeffs_id = toneid + 6
        toneset.band2_freq_count = 4

        # Original values:
        # toneset.req_third_peak = 0.0794
        # toneset.req_signal_to_noise_ratio = 0.756
        # toneset.req_minimum_power = 1.0e8
        # toneset.req_twist_for_dual_tone = 10.0

        # Tweaked values
        toneset.req_third_peak = 0.5
        toneset.req_signal_to_noise_ratio = 0.756
        toneset.req_minimum_power = 1.0e8
        toneset.req_twist_for_dual_tone = 50.0

        rc = lowlevel.sm_add_input_tone_set(toneset)
        if rc:
            raise AculabError(rc, 'sm_add_input_freq_coeffs')        

        self.dtmf_fax_toneset_id = toneset.id
        
        return self.dtmf_fax_toneset_id

    def translate_tone(self, toneset, mode, recog):
        """Translate for our custom DTMF/FAX toneset.

        @return: a tuple (tone, length).
        length will be None unless une of the C{kSMToneLenDetection*}
        algorithms is used.
        """
        
        l = None
        if toneset == self.dtmf_fax_toneset_id:
            # Sigh. The parameters are in different places depending
            # on the tone detection type
            if mode in (lowlevel.kSMToneLenDetectionNoMinDuration,
                        lowlevel.kSMToneLenDetectionMinDuration64,
                        lowlevel.kSMToneLenDetectionMinDuration40):
                p = (recog.param0/256, recog.param0 % 256)
                l = recog.param1

            else:
                p = (recog.param0, recog.param1)

            return (self.dtmf_fax_tonematrix[p[0]][p[1]], l)
                        
        else:
            ValueError('unknown toneset id %d' % toneset_id)

    def vmptx_default_toneset(self):
        """Allocate a default toneset for the VMPtx on the first invocation
        and cache it for subsequent invocations."""
        
        if self.vmptx_toneset_id:
            return self.vmptx_toneset_id

        ts = lowlevel.SM_VMPTX_CREATE_TONESET_PARMS()

        ts.module = self.info.module
        ts.set_default_toneset()
        rc = lowlevel.sm_vmptx_create_toneset(ts)
        if rc:
            raise AculabError(rc, 'sm_vmptx_create_toneset')       

        self.vmptx_toneset_id = ts.tone_set_id

        return self.vmptx_toneset_id

class ProsodyCard(Card):
    """An Aculab Prosody (speech processing) card.
    """
    def __init__(self, card, info):
        Card.__init__(self, card, info)
        
        self.ip_address = None
        open_prosp = lowlevel.ACU_OPEN_PROSODY_PARMS()

        open_prosp.card_id = card.card_id
        rc = lowlevel.acu_open_prosody(open_prosp)
        if rc:
            raise AculabError(rc, '%s acu_open_prosody' % self.card.serial_no)

        sm_infop = lowlevel.SM_CARD_INFO_PARMS()
        sm_infop.card = card.card_id
        rc = lowlevel.sm_get_card_info(sm_infop)
        if rc:
            raise AculabError(rc, '%s sm_get_card_info' % self.card.serial_no)
            
        self.modules = [Module(card, i) for i in range(sm_infop.module_count)]

        if sm_infop.card_type == lowlevel.kSMCarrierCardTypePX:
            ipinfo = lowlevel.ACU_PROSODY_IP_CARD_REGISTRATION_PARMS()
            
            ipinfo.card = self.card.serial_no
            
            rc = lowlevel.acu_get_prosody_ip_card_config(ipinfo)
            if rc:
                raise AculabError(rc, '%s acu_get_prosody_ip_card_config' \
                                  % self.card.serial_no)

            self.ip_address = ipinfo.ip4_address;

    def __repr__(self):
        if self.ip_address:
            return 'ProsodyCard(%s, %s)' \
                   % (self.card.serial_no, self.ip_address)
        else:
            return 'ProsodyCard(%s)' % self.card.serial_no

count = 0

class Snapshot(object):

    # This class is a singleton
    _singleton = None # our singleton reference
    def __new__(cls, *args, **kwargs):
        if Snapshot._singleton is None:
            Snapshot._singleton = object.__new__(cls)
            Snapshot._singleton.init(*args, **kwargs)
        return Snapshot._singleton

    def init(self, notification_queue = None, user_data = None):
        """Note that we do not have a __init__ method, since this is called
        every time the singleton is re-issued. We do the work here instead"""
        
        self.sip = None
        self.switch = []
        self.call = []
        self.prosody = []

        global count
        if count > 0:
            raise RuntimeError
        
        count = count + 1

        rc, sip_port = lowlevel.sip_open_port()
        # Don't fail if no SIP service is running
        if rc == 0:
            self.sip = sip_port
        
        snapshotp = lowlevel.ACU_SNAPSHOT_PARMS()
    
        rc = lowlevel.acu_get_system_snapshot(snapshotp)
        if rc:
            raise AculabError(rc, 'acu_get_snapshot_parms')
    
        for i in range(snapshotp.count):
            openp = lowlevel.ACU_OPEN_CARD_PARMS()
            openp.serial_no = snapshotp.get_serial(i)
            openp.app_context_token = user_data
            openp.notification_queue = notification_queue
            rc = lowlevel.acu_open_card(openp)
            if rc:
                raise AculabError(rc, 'acu_open_card')

            infop = lowlevel.ACU_CARD_INFO_PARMS()
            infop.card_id = openp.card_id
            rc = lowlevel.acu_get_card_info(infop)
            if rc:
                raise AculabError(rc, 'acu_get_card_info')

            if infop.resources_available & lowlevel.ACU_RESOURCE_SWITCH:
                self.switch.append(SwitchCard(openp, infop))

            if infop.resources_available & lowlevel.ACU_RESOURCE_CALL:
                self.call.append(CallControlCard(openp, infop))

            if infop.resources_available & lowlevel.ACU_RESOURCE_SPEECH:
                self.prosody.append(ProsodyCard(openp, infop))


    def pprint(self, **kwargs):
        """Pretty-print all cards (not very detailed yet)"""
        
        pp = PrettyPrinter(*kwargs)

        pp.pprint(self.switch)
        pp.pprint(self.call)
        pp.pprint(self.prosody)

        

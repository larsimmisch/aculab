"""A snapshot of all available cards, ports and modules (v6 API and later)."""

from pprint import PrettyPrinter
import lowlevel
from busses import ProsodyLocalBus
from error import AculabError

_singletons = {}


class Card(object):
    """Base class for an Aculab card."""
    def __init__(self, card, info):
        self.card = card
        self.info = info

class SwitchCard(Card):
    """An Aculab card with a switch matrix."""
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
    """A port on an Aculab call control card."""
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
    """An Aculab card capable of call control."""
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

        self.ports = [Port(card, i) for i in range(infop.ports)]

    def __repr__(self):
        return 'CallControlCard(%s)' % self.card.serial_no
            
class Module(object):
    """A DSP module on an Aculab Prosody (speech processing) card."""
    def __init__(self, card, index):
        sm_openp = lowlevel.SM_OPEN_MODULE_PARMS()

        sm_openp.card_id = card.card_id
        sm_openp.module_ix = index
        rc = lowlevel.sm_open_module(sm_openp)
        if rc:
            raise AculabError(rc, 'sm_open_module')

        self.open = sm_openp

        self.info = lowlevel.SM_MODULE_INFO_PARMS()
        self.info.module = sm_openp.module_id
        rc = lowlevel.sm_get_module_info(self.info)
        if rc:
            raise AculabError(rc, 'sm_get_module_info')

        self.timeslots = ProsodyLocalBus(self.info.min_stream)

class ProsodyCard(Card):
    """An Aculab Prosody (speech processing) card."""
    def __init__(self, card, info):
        Card.__init__(self, card, info)
    
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

    def __repr__(self):
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
        
        self.switch = []
        self.call = []
        self.prosody = []

        global count
        if count > 0:
            raise RuntimeError
        
        count = count + 1
        
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
        pp = PrettyPrinter(*kwargs)

        pp.pprint(self.switch)
        pp.pprint(self.call)
        pp.pprint(self.prosody)

        

import lowlevel
from error import AculabError

class Card:
    def __init__(self, card, info):
        self.card = card
        self.info = info

class SwitchCard(Card):
    def __init__(self, card, info):
        Card.__init__(self, card, info)
        
        switchp = lowlevel.ACU_OPEN_SWITCH_PARMS()
        switchp.card_id = card.card_id
        rc = lowlevel.acu_open_switch(switchp)
        if rc:
            raise AculabError(rc, 'acu_open_switch()')

        self.open = switchp

class Port:
    def __init__(self, card, index):
        open_portp = lowlevel.OPEN_PORT_PARMS()

        open_portp.card_id = card.card_id
        open_portp.port_ix = index

        rc = lowlevel.call_open_port(open_portp)
        if rc:
            raise AculabError(rc, 'call_open_port()')

        info_portp = lowlevel.PORT_INFO_PARMS()
        info_portp.port_id = open_portp.port_id

        rc = lowlevel.call_port_info(info_portp)
        if rc:
            raise AculabError(rc, 'call_open_port()')

        self.open = open_portp
        self.info = info_portp
        
class CallControlCard(Card):
    def __init__(self, card, info):
        Card.__init__(self, card, info)

        callp = lowlevel.ACU_OPEN_CALL_PARMS()
        callp.card_id = card.card_id
        rc = lowlevel.acu_open_call(callp)
        if rc:
            raise AculabError(rc, 'acu_open_call()')

        infop = lowlevel.CARD_INFO_PARMS()
        infop.card_id = card.card_id
        rc = lowlevel.call_get_card_info(infop)
        if rc:
            raise AculabError(rc, 'call_get_card_info()')

        self.ports = [Port(card, i) for i in range(infop.ports)]
            
class Module:
    def __init__(self, card, index):
        sm_openp = lowlevel.SM_OPEN_MODULE_PARMS()

        sm_openp.card_id = card.card_id
        sm_openp.module_ix = index
        rc = lowlevel.sm_open_module(sm_openp)
        if rc:
            raise AculabError(rc, 'sm_open_module()')    

class ProsodyCard(Card):
    def __init__(self, card, info):
        Card.__init__(self, card, info)
    
        open_prosp = lowlevel.ACU_OPEN_PROSODY_PARMS()

        open_prosp.card_id = card.card_id
        rc = lowlevel.acu_open_prosody(open_prosp)
        if rc:
            raise AculabError(rc, 'acu_open_prosody()')

        sm_infop = lowlevel.SM_CARD_INFO_PARMS()
        sm_infop.card = card.card_id
        rc = lowlevel.sm_get_card_info(sm_infop)
        if rc:
            raise AculabError(rc, 'sm_get_card_info()')

        self.modules = [Module(card, i) for i in range(sm_infop.module_count)]

class Snapshot:    
    def __init__(self):
        self.switch = []
        self.call = []
        self.prosody = []
        
        snapshotp = lowlevel.ACU_SNAPSHOT_PARMS()
    
        rc = lowlevel.acu_get_system_snapshot(snapshotp)
        if rc:
            raise AculabError(rc, 'acu_get_snapshot_parms()')
    
        for i in range(snapshotp.count):
            openp = lowlevel.ACU_OPEN_CARD_PARMS()
            openp.serial_no = snapshotp.get_serial(i)
            rc = lowlevel.acu_open_card(openp)
            if rc:
                raise AculabError(rc, 'acu_open_card()')

            infop = lowlevel.ACU_CARD_INFO_PARMS()
            infop.card_id = openp.card_id
            rc = lowlevel.acu_get_card_info(infop)
            if rc:
                raise AculabError(rc, 'acu_get_card_info()')

            if infop.resources_available & lowlevel.ACU_RESOURCE_SWITCH:
                self.switch.append(SwitchCard(openp, infop))

            if infop.resources_available & lowlevel.ACU_RESOURCE_CALL:
                self.call.append(CallControlCard(openp, infop))

            if infop.resources_available & lowlevel.ACU_RESOURCE_SPEECH:
                self.prosody.append(ProsodyCard(openp, infop))


                

#!/usr/bin/env python

# Copyright (C) 2007 Lars Immisch

from aculab.snapshot import Snapshot
from aculab.error import AculabError
import aculab.lowlevel as lowlevel

if __name__ == '__main__':

    for card in Snapshot().call:
        print card
        for port in card.ports:
            unblock = lowlevel.PORT_BLOCKING_XPARMS()
            unblock.net = port.open.port_id
            unblock.flags = lowlevel.ACU_MAINT_ETS_D_CHAN
            unblock.unique_xparms.ts_mask = 0x7ffff

            rc = lowlevel.call_maint_port_unblock(unblock)
            if rc:
                print '    %s: %s' % \
                      (port, AculabError(rc, 'call_main_port_unblock'))
            else:
                print '    %s: unblocked' % port

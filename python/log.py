#!/usr/bin/env python

import aculab.lowlevel as al
from aculab.snapshot import Snapshot
from aculab.error import AculabError
from time import sleep

if __name__ == '__main__':

    card = 2
    port = 2

    snapshot = Snapshot()

    port = snapshot.call[card].ports[port].open.port_id

    l1 = al.L1_XSTATS()
    l1.net = port
    rc = al.call_l1_stats(l1)

    print l1.get.clock
    
    log = al.LOG_XPARMS()

    while True:
        log.clear()
        log.net = port
        rc = al.call_protocol_trace(log)
        if rc:
            raise AculabError(rc, 'call_protocol_trace')

        rxtx = log.log.RxTx
        timestamp = log.log.TimeStamp
        packet = log.log.Data_Packet

        l = 0
        if packet:
            l = ord(packet[0])
            print repr(packet[:5])
        if  l > 5:
            packet = packet[5:l+5]
        else:
            packet = None

        if packet:
            print rxtx, timestamp, l, repr(packet)
        else:
            sleep(0.05)



#!/usr/bin/env python

import aculab.lowlevel as al
from aculab.snapshot import Snapshot
from aculab.error import AculabError
from time import sleep

if __name__ == '__main__':

    card = 0
    port = 0

    snapshot = Snapshot()

    port = snapshot.call[card].ports[port].open.port_id

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

        if packet and ord(packet[0]) > 5:
            packet = packet[5:ord(packet[0])+5]
        else:
            packet = None

        if packet:
            print rxtx, timestamp, repr(packet)
        else:
            sleep(0.05)



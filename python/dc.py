#!/usr/bin/env python

import sys
import os
import getopt
import logging
import struct
import time
import aculab
import aculab.lowlevel as lowlevel
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.speech import SpeechChannel, SpeechDispatcher, Glue
from aculab.busses import DefaultBus

data = lowlevel.SMDC_DATA_PARMS()
data.allocbuffer(320)

f = open('raw.al', 'w')

class DCController:

    def dc_read(self):
        global channels
        global data
        global f

        status = lowlevel.SMDC_RX_STATUS_PARMS()
        status.channel = channels[0].channel

        rc = lowlevel.smdc_rx_status(status)
        if rc:
            raise AculabError(rc, 'smdc_line_status')

        # print 'status: %d, %d' % (status.status, status.available_octets)
                
        data.channel = channels[0].channel

        rc = lowlevel.smdc_rx_data(data)
        if rc:
            raise AculabError(rc, 'smdc_rx_data')

        d = data.getdata_bitrev()

        f.write(d)

    def play_done(self, channel, f, reason, position, user_data, job_data):
        print "play_done"
        f.close()
        sys.exit(2)

def usage():
    print 'usage: dc.py [-c <card>] [-m <module>]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    card = 0
    module = 0
    controller = DCController()

    options, args = getopt.getopt(sys.argv[1:], 'c:m:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        else:
            usage()

    snapshot = Snapshot()

    channels = [SpeechChannel(controller, card, module),
                SpeechChannel(controller, card, module)]

    connection = channels[0].connect(channels[1])

    for i in (0, 1):
        print "[%d] %d:%d" % (i, channels[i].info.ost, channels[i].info.ots)

    channels[1].play('greeting.al')

    channels[0].dc_config(lowlevel.kSMDCProtocolRawRx, None,
                          lowlevel.kSMDCConfigEncodingSync, None)

    channels[0].dispatcher.add(channels[0].event_read, controller.dc_read)
    channels[0].dc_rx_control(lowlevel.kSMDCRxCtlNotifyOnData, 160, 0, 0)
    
    
    SpeechDispatcher.run()

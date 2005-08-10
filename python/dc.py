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
from aculab.speech import SpeechChannel, SpeechDispatcher, DCReadJob
from aculab.busses import DefaultBus


f = open('raw.al', 'w')

class Model:
    def __init__(self, controller, card, module):

        self.controller = controller
        self.card = card
        self.module = module
        
        self.data = lowlevel.SMDC_DATA_PARMS()
        self.data.allocbuffer(320)

        self.channels = [SpeechChannel(controller, card, module,
                                       user_data=self),
                         SpeechChannel(controller, card, module,
                                       user_data=self)]

        self.connection = self.channels[0].connect(self.channels[1])

    def reinit(self):
        del self.connection
        del self.channels
            
        self.channels = [SpeechChannel(controller, card, module),
                         SpeechChannel(controller, card, module)]

        self.connection = self.channels[0].connect(self.channels[1])

    def start(self):
        self.dc_read = DCReadJob(lowlevel.kSMDCRxCtlNotifyOnData, 160, 0, 0)
        
        self.channels[1].play('greeting.al')

        self.channels[0].dc_config(lowlevel.kSMDCProtocolRawRx, None,
                                   lowlevel.kSMDCConfigEncodingSync, None)


        self.channels[0].start(self.dc_read)

    
class DCController:

    def dc_read(self, channel):

        model = channel_user_data

        status = lowlevel.SMDC_RX_STATUS_PARMS()
        status.channel = channel.channel

        rc = lowlevel.smdc_rx_status(status)
        if rc:
            raise AculabError(rc, 'smdc_line_status')

        # print 'status: %d, %d' % (status.status, status.available_octets)
                
        data.channel = channel.channel

        rc = lowlevel.smdc_rx_data(data)
        if rc:
            raise AculabError(rc, 'smdc_rx_data')

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



    m = Model(controller, card, module)
    
    SpeechDispatcher.run()

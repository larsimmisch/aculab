#!/usr/bin/env python

import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *
from aculab.lowlevel import *

class OutgoingCallController:

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

    def ev_idle(self, call, model):
        print call.feature_details.feature.facility.length
        openout(call, args[0])
        
def usage():
    print 'mwi.py [-p <port>] <number>'
    sys.exit(-2)

def openout(call, dest):
    feature_data = FEATURE_UNION()
    feature_data.facility.setdata('\x91\xA1\x35\x02\x02\x67\xF9\x06\x06\x04'
                                  '\x00\x85\x69\x01\x02\x30\x27\xA1\x0E\x0A'
                                  '\x01\x00\x12\x09\x30\x35\x35\x32\x38\x32'
                                  '\x38\x36\x30\x0A\x01\x00\xA1\x0F\x0A\x01'
                                  '\x02\x12\x0A\x38\x30\x30\x33\x33\x30\x32'
                                  '\x34\x32\x34\x0A\x01\x02')

    call.openout(dest, feature = FEATURE_REGISTER + FEATURE_FACILITY,
                 feature_data = feature_data, originating_address='41',
                 cnf = lowlevel.CNF_TSVIRTUAL)

if __name__ == '__main__':
    port = 0
    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        else:
            usage()

    if not len(args):
        usage()

    calldispatcher = CallEventDispatcher()

    c = CallHandle(controller, calldispatcher, port=port)
    openout(c, args[0])
    
    calldispatcher.run()

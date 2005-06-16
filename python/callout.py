#!/usr/bin/env python

import sys
import getopt
import struct
from aculab.error import AculabError
from aculab.snapshot import Snapshot
from aculab.callcontrol import *

class OutgoingCallController:

    def ev_outgoing_ringing(self, call, model):
        log.debug('%s stream: %d timeslot: %d', call.name,
                  call.details.stream, call.details.ts)

    def ev_remote_disconnect(self, call, model):
        call.disconnect()

class RepeatedOutgoingCallController:

    def ev_idle(self, call, model):
        call.user_data = model
        call.openout(model, 1, model)

def usage():
    print 'callout.py [-n <number of calls>] [-p <port>] [-r] number'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    card = 0
    timeslot = None

    log = aculab.defaultLogging(logging.DEBUG)

    controller = OutgoingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:rt:')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-r':
            controller = RepeatedOutgoingCallController()
        elif o == '-t':
            timeslot = int(a)
        else:
            usage()

    if not len(args):
        usage()

    snapshot = Snapshot()
    port = snapshot.call[card].ports[port].open.port_id

    fd = lowlevel.FEATURE_UNION()

    fd.uui.command = lowlevel.UU_DATA_CMD
    fd.uui.request = lowlevel.UUS_1_IMPLICITLY_PREFERRED
    fd.uui.control = lowlevel.CONTROL_NEXT_CC_MESSAGE
    fd.uui.protocol = lowlevel.UUI_PROTOCOL_USER_SPECIFIC
    fd.uui.data = 'Hallo Hauke'
    fd.uui.length = len(fd.uui.data) + 1
    
    c = Call(controller,  port=port, timeslot=timeslot)
    c.user_data = '41'
    c.openout(args[0], 1, c.user_data, feature = lowlevel.FEATURE_USER_USER,
              feature_data = fd)

    fd.raw_data.length = 6
    fd.raw_data.data = struct.pack('BBBBBB',
                                   2, # See Appendix M, Aculab Call Control
                                   0x9f, 0x01, 0x02, 0, 0)

    c.feature_send(lowlevel.FEATURE_RAW_DATA,
                   lowlevel.CONTROL_LAST_INFO_SETUP, fd)

    CallDispatcher.run()

#!/usr/bin/env python

import sys
import getopt
from aculab.error import AculabError
from aculab.lowlevel import *
from aculab.callcontrol import *

class VirtualCallController:

    def ev_call_connected(self, call):
        call.release()

class RepeatedVirtualCallController(VirtualCallController):

    def ev_idle(self, call):
        call.openin()

def usage():
    print 'usage: virtual.py [-p <port>] [-t <timeslot>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    timeslot = -1
    controller = VirtualCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:t:r?')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-t':
            timeslot = int(a)
        elif o == '-r':
            controller = RepeatedVirtualCallController()
        else:
            usage()
                
    calldispatcher = CallEventDispatcher()
    
    c = CallHandle(controller, calldispatcher, port=port, timeslot=timeslot)
    c.openin(cnf=lowlevel.CNF_TSVIRTUAL)

    calldispatcher.run()

#!/usr/bin/env python

# Copyright (C) 2004-2007 Lars Immisch

import sys
from aculab.error import AculabError
from aculab.reactor import CallReactor
from aculab.lowlevel import *
from aculab.callcontrol import *

class VirtualCallController:

    def ev_call_connected(self, call):
        details = call.get_details()
        print 'feature:', details.feature_information
        call.release()

class RepeatedVirtualCallController(VirtualCallController):

    def ev_idle(self, call):
        call.openin()

if __name__ == '__main__':

    parser = aculab.defaultOptions(
        description='Wait for and accept an incoming virtual call.',
        repeat=True)

    parser.add_option('-n', '--numcalls', action='store', type='int',
                      default=1, help='Accept NUMCALLS in parallel')

    options, args = parser.parse_args()

    controller = VirtualCallController()

    for i in range(options.numcalls):
            c = CallHandle(controller, card=options.card,
                           port=options.port, timeslot=-1)
            c.openin(cnf=lowlevel.CNF_TSVIRTUAL)

    CallReactor.run()

#!/usr/bin/env python

import sys
import os
import getopt
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel, PlayJob
from aculab.switching import DefaultBus
from aculab.timer import TimerThread
from aculab.snapshot import Snapshot
from aculab.connect import connect, Glue
from aculab.reactor import CallReactor, SpeechReactor
import aculab.lowlevel as lowlevel

class PlayApp(Glue):

    def __init__(self, controller, module, call):
        super(PlayApp, self).__init__(controller, module, call)
        self.timer = None

    def start(self):
        # start a timer to accept the call later
        self.timer = timer.add(2.0, self.timed_switch)

    def close(self):
        super(PlayApp, self).close()
        if self.timer:
            timer.cancel(self.timer)

    def timed_switch(self):
        self.connections = connect(self.call, self.speech)
        self.speech.start(PlayJob(self.speech, fplay))

        # self.timer = timer.add(2.0, self.timed_unswitch)

    def timed_unswitch(self):
        del self.connections
        self.timer = timer.add(2.0, self.timed_disconnect)

    def timed_disconnect(self):
        self.call.disconnect()

    def job_done(self, job, reason):
        log.debug('play done')
        del self.connections
        self.timer = timer.add(2.0, self.timed_disconnect)
        
class PlayController(object):

    def ev_incoming_call_det(self, call, user_data):
        cli = call.details.originating_addr
        log.info('%s called: %s calling: %s stream: %d timeslot: %d',
                 call.name, call.details.destination_addr, cli,
                 call.details.stream, call.details.ts)

        call.user_data = PlayApp(self, module, call)
        call.accept()
        
    def ev_call_connected(self, call, user_data):
        user_data.start()
        
    def ev_remote_disconnect(self, call, user_data):
        if user_data:
            user_data.speech.stop()

    def ev_idle(self, call, user_data):
        raise StopIteration

    def play_done(self, channel, f, reason, position, user_data):
        pass

    def job_done(self, job, reason, user_data):
        user_data.job_done(job, reason)
        
    def digits_done(self, channel, user_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        log.info('got DTMF: %s', digit)

def usage():
    print 'usage: play.py [-c <card>] [-p <port>] [-m <module>] <file>'
    sys.exit(2)

if __name__ == '__main__':

    card = 0
    port = 0
    module = 0
    numcalls = 1
    fplay = None
    loglevel = logging.DEBUG

    options, args = getopt.getopt(sys.argv[1:], 'c:m:p:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-p':
            port = int(a)
        else:
            usage()

    if not args:
        usage()

    unblock = lowlevel.PORT_BLOCKING_XPARMS()
    unblock.net = Snapshot().call[card].ports[port].open.port_id
    unblock.flags = lowlevel.ACU_MAINT_ETS_D_CHAN
    unblock.ts_mask = 0x7ffff

    lowlevel.call_maint_port_unblock(unblock)

    fplay = args[0]

    controller = PlayController()

    log = aculab.defaultLogging(loglevel)

    try:
        bus =  DefaultBus()

        log.info('play app starting (bus: %s)',
                bus.__class__.__name__)

        for i in range(numcalls):
            c = Call(controller, card=card, port=port)

        timer = TimerThread()
        timer.start()
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass
    except:
        log.error('play app exception', exc_info=1)

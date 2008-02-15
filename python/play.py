#!/usr/bin/env python

# Copyright (C) 2004-2007 Lars Immisch

import sys
import os
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel, PlayJob, Glue
from aculab.switching import DefaultBus, connect
from aculab.timer import TimerThread
from aculab.snapshot import Snapshot
from aculab.reactor import CallReactor, SpeechReactor
import aculab.lowlevel as lowlevel

class PlayApp(Glue):

    def __init__(self, controller, module, call):
        Glue.__init__(self, controller, module, call, False)
        self.speech.listen_for()
        self.timer = None
        self.jobs = [PlayJob(self.speech, fn) for fn in fplay]
        self.iter = self.job_generator()

    def job_generator(self):
        for j in self.jobs:
            yield j

    def start(self):
        # start a timer to play the prompt in 2 seconds
        self.timer = timer.add(2.0, self.timed_switch)

    def close(self):
        Glue.close(self)
        if self.timer:
            timer.cancel(self.timer)

    def timed_switch(self):
        self.connection = connect(self.call, self.speech, force_bus=True)
        j = self.iter.next()
        if j:
            self.speech.start(j)

        # self.timer = timer.add(2.0, self.timed_unswitch)

    def timed_unswitch(self):
        self.connection.close()
        self.connection = None
        self.timer = timer.add(2.0, self.timed_disconnect)

    def timed_disconnect(self):
        self.call.disconnect()

    def job_done(self, job, reason):
        log.debug('play done')
        try:
            # disconnect and reconnect for Bob, to show silent switching
            self.connection.close()
            self.connection = connect(self.call, self.speech)
            j = self.iter.next()
            self.speech.start(j)
        except StopIteration:
            self.connection.close()
            self.connection = None
            self.timer = timer.add(2.0, self.timed_disconnect)
        
class PlayController(object):

    def ev_incoming_call_det(self, call, user_data):
        cli = call.details.originating_addr
        log.info('%s called: %s calling: %s stream: %d timeslot: %d',
                 call.name, call.details.destination_addr, cli,
                 call.details.stream, call.details.ts)

        call.user_data = PlayApp(self, options.module, call)
        call.accept()
        
    def ev_call_connected(self, call, user_data):
        user_data.start()
        
    def ev_remote_disconnect(self, call, user_data):
        if user_data:
            user_data.speech.stop()

    def ev_idle(self, call, user_data):
        raise StopIteration

    def play_done(self, channel, reason, f, duration, user_data):
        pass

    def job_done(self, job, reason, user_data):
        user_data.job_done(job, reason)
        
    def digits_done(self, channel, user_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        log.info('got DTMF: %s', digit)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)
    
    parser = aculab.defaultOptions(
        usage='usage: %prog [options] file+',
        description='Accept incoming PSTN calls and play file(s).')

    parser.add_option('-n', '--numcalls', action='store', type='int',
                      default=1, help='Accept NUMCALLS in parallel')

    options, args = parser.parse_args()

    if not args:
        parser.print_help()
        sys.exit(2)

    fplay = args

    controller = PlayController()

    try:
        bus =  DefaultBus()

        log.info('play app starting (bus: %s)',
                bus.__class__.__name__)

        for i in range(options.numcalls):
            c = Call(controller, card=options.card, port=options.port)

        timer = TimerThread()
        timer.start()
        SpeechReactor.start()
        CallReactor.run()
    except StopIteration:
        pass
    except:
        log.error('play app exception', exc_info=1)

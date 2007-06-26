#!/usr/bin/env python

import sys

sys.path.extend(['.', '..'])

import os
import getopt
import logging
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel, PlayJob, RecordJob
from aculab.reactor import CallReactor, SpeechReactor
from aculab.busses import DefaultBus
from aculab.timer import TimerThread
from aculab.connect import Glue
import aculab.lowlevel as lowlevel
from mail import AsyncEmail
from slim import async_cli_display

# Modify this to change the time the answering machine waits before accepting
# the call
wait_accept = 20.0

# application map
portmap = { '41': 'am', '42': 'am', '43': 8, '44': 8,
            '45': 9, '46': 9, '47': 1, '48': 1 }

class AnsweringMachine(Glue):
    def __init__(self, controller, module, call):
        super(self.__class__, self).__init__(controller, module, call)

        # start a timer to accept the call later
        self.timer = timer.add(wait_accept, self.on_timer)

    def close(self):
        super(self.__class__, self).close()
        if self.timer:
            timer.cancel(self.timer)

    def on_timer(self):
        self.timer = None
        self.call.accept()

    def start(self):
        self.timer = None
        f = os.path.join(root, '%s.al' % self.call.details.destination_addr)
        if os.path.exists(f):
            announce = PlayJob(self.speech, f)
        else:
            announce = PlayJob(self.speech, os.path.join(root, 'default.al'))
            
        self.jobs = [PlayJob(self.speech,
                             os.path.join(root,
                                          '4011_suonho_sweetchoff_' \
                                          'iLLCommunications_suonho.al')),
                     announce,
                     PlayJob(self.speech, os.path.join(root, 'beep.al')),
                     RecordJob(self.speech, os.tmpfile(), max_silence=4.0)]

        self.speech.start(self.jobs[0])

    def job_done(self, job, reason):
        i = self.jobs.index(job)
        if i < len(self.jobs) - 1:
            if reason is None:
                log.debug('next job: %d', i + 1)
                self.speech.start(self.jobs[i + 1])
            else:
                self.call.disconnect()
        else:
            log.debug('recording terminated: %s', reason)
            job.file.seek(0)
            # only send recordings with more than a second of speech
            if job.duration - job.max_silence > 1.0 and not test_run:
                # job.file will be closed by AsyncEmail.run
                # the call will be hungup from AsyncEmail.run, too
                e = AsyncEmail(job.file, self.call)
                e.start()
            else:
                if test_run:
                    log.info('call from %s discarded - test run. speech: %.3f',
                             self.call.details.originating_addr,
                             job.duration - job.max_silence)
                else:
                    log.info('call from %s too short: %.3f',
                             self.call.details.originating_addr,
                             job.duration - job.max_silence)
                self.call.disconnect()                    

class AMController(object):
        
    def ev_call_connected(self, call, user_data):        
        user_data.start()
        
    def ev_remote_disconnect(self, call, user_data):
        if user_data:
            user_data.speech.stop()

    def ev_idle(self, call, user_data):
        if user_data:
            user_data.close()
        call.user_data = None
        call.pop_controller()
        call.openin()

    def play_done(self, channel, f, reason, position, user_data):
        pass

    def record_done(self, channel, f, reason, position, user_data):
        pass

    def job_done(self, job, reason, user_data):
        user_data.job_done(job, reason)
        
    def digits_done(self, channel, user_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        log.info('got DTMF: %s', digit)

def routing_table(port, details):
    """Returns the tuple (cause, port, timeslot, destination_address,
    originating_address)
    If cause is not none, hangup"""
    
    if not details.destination_addr and details.sending_complete:
        return (lowlevel.LC_CALL_REJECTED, None, None, None)

    if port == 0:
        # only forward local calls
        # if details.originating_addr in [str(i) for i in range(31, 39)]:
        if True:
            return (None, portmap[details.destination_addr],
                    details.ts, details.destination_addr,
                    details.originating_addr)
        else:
            return (None, None, None, None, None)
        
    elif port in [8, 9]:
        if not details.sending_complete:
            return (None, None, None, None)
        else:
            if details.destination_addr[0] in ['8', '9']:
                p = int(details.destination_addr[0])
                ts = details.ts
                # kludge to get call back on the same port working without
                # glare
                if p == port:
                    if ts < 16:
                        ts += 16
                    else:
                        ts -= 16
                return (None, p, ts, details.destination_addr,
                        details.originating_addr)
            else:
                return (None, 0, details.ts,
                        details.destination_addr, details.originating_addr)
    else:
        return (lowlevel.LC_NUMBER_BUSY, None, None, None, None)

def find_available_call(port, ts = None, exclude = None):
    global calls
    for c in calls:
        if c.port == port and c != exclude \
           and (c.last_event == lowlevel.EV_WAIT_FOR_INCOMING 
                or c.last_event == lowlevel.EV_IDLE):
            if ts is None or ts == c.timeslot:
                return c

    return None

class Forward:
    def __init__(self, incall):
        self.incall = incall
        self.outcall = None
        self.connections = []

        self.route()

    def route(self):
        self.incall.user_data = self

        if self.outcall:
            # warning: untested (and probably flawed)
            print hex(self.outcall.handle), 'sending:', d.destination_addr
            self.outcall.send_overlap(d.destination_addr,
                                      d.sending_complete)
        else:
            cause, port, timeslot, number, cli = \
                   routing_table(self.incall.port, self.incall.details)

            if port != None and number:
                print hex(self.incall.handle), \
                      'making outgoing call on port %d to %s' % (port,  number)
                self.outcall = find_available_call(port, timeslot, self.incall)
                if not self.outcall:
                    print hex(self.incall.handle), 'no call available'
                    self.incall.disconnect(lowlevel.LC_NUMBER_BUSY)
                else:
                    self.outcall.push_controller(fwcontroller)
                    self.outcall.user_data = self
                    self.outcall.openout(number, 1, cli)
            elif cause:
                self.incall.disconnect(cause)
            else:
                print hex(self.incall.handle), \
                      'waiting - no destination address'

    def connect(self):
        """Connects incoming and outgoing call. Can be called more than
        once, but will create the connection only on the first invocation."""
        if not self.connections:
            slots = [bus.allocate(), bus.allocate()]

            c = [self.incall.speak_to(slots[0]),
                 self.outcall.listen_to(bus.invert(slots[0])),
                 self.outcall.speak_to(slots[1]),
                 self.incall.listen_to(bus.invert(slots[1]))]

            self.connections.extend(c)

    def disconnect(self):
        for c in self.connections:
            if c.ts[0] < 16:
                bus.free(c.ts)

        self.connections = []
        
class ForwardCallController:
    "controls a single incoming call and its corresponding outgoing call"

    def ev_outgoing_ringing(self, call, model):
        if model.incall and model.outcall:
            model.connect()

    def ev_call_connected(self, call, model):
        if call != model.incall:
            model.connect()
            model.incall.accept()

    def ev_remote_disconnect(self, call, model):
        # if both calls hang up at the same time, disconnect will be called
        # twice, because the calls are set to None only in ev_idle.
        # This should not matter, however.

        # pass on cause values
        cause = call.get_cause()
        if model:
            if call == model.incall:
                if model.outcall:
                    model.outcall.disconnect(cause)
            elif call == model.outcall:
                if model.incall:
                    model.incall.disconnect(cause)

        call.disconnect()

    def ev_idle(self, call, model):
        if model:
            model.disconnect()
        
            if call == model.incall:
                if model.outcall:
                    model.outcall.disconnect()            
            elif call == model.outcall:
                if model.incall:
                    call.user_data.incall.disconnect()
                
            call.user_data = None

        if not call.handle:
            call.pop_controller()
            call.openin()

class IncomingCallController(object):
    def ev_incoming_call_det(self, call, user_data):
        cli = call.details.originating_addr
        log.info('%s called: %s calling: %s stream: %d timeslot: %d',
                 call.name, call.details.destination_addr, cli,
                 call.details.stream, call.details.ts)

        log.debug('portmap: %s',
                  portmap.get(call.details.destination_addr, None))

        if portmap.get(call.details.destination_addr, None) == 'am':
            if cli:
                async_cli_display(cli)

            # Let AMController take over.
            log.debug('starting timer for answering machine')
            call.push_controller(amcontroller)
            call.user_data = AnsweringMachine(amcontroller, module, call)
            call.incoming_ringing()
        elif forwarding:
            log.debug('starting forwarding')
            call.push_controller(fwcontroller)
            call.user_data = Forward(call)
            call.incoming_ringing()

def usage():
    print \
"""Synopsis: am.py [-c <card>] [-p <port>] [-m <module>] [-d] [-t] [-f]

Options:
  -d: daemonize
  -t: test run
  -f: enable forwarding"""
    
    sys.exit(2)

if __name__ == '__main__':

    card = 0
    port = 0
    module = 0
    daemon = False
    logfile = None
    test_run = False
    forwarding = False
    loglevel = logging.DEBUG
    root = os.getcwd()

    options, args = getopt.getopt(sys.argv[1:], 'c:dm:p:r:tfh?')

    for o, a in options:
        if o == '-c':
            card = int(a)
        elif o == '-d':
            daemon = True
            # loglevel = logging.INFO
            logfile = '/var/log/am.log'
        elif o == '-m':
            module = int(a)
        elif o == '-p':
            port = int(a)
        elif o == '-r':
            root = a
        elif o == '-t':
            test_run = True
        elif o == '-f':
            forwarding = True
        else:
            usage()

    controller = IncomingCallController()
    amcontroller = AMController()
    fwcontroller = ForwardCallController()

    log = aculab.defaultLogging(loglevel, logfile)

    if forwarding:
        bri_ts = (1, 2)

        e1_ts = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31)

        # On V6, we could look at the snapshot, but this code
        # is installation specific anyway
        calls = [Call(controller, None, port=0, timeslot=t) for t in bri_ts]
        calls += [Call(controller, None, port=1, timeslot=t) for t in bri_ts]
        calls += [Call(controller, None, port=8, timeslot=t) for t in e1_ts]
        calls += [Call(controller, None, port=9, timeslot=t) for t in e1_ts]
    else:
        calls = [Call(controller, card=card, port=port)]

    if daemon:
        aculab.daemonize(pidfile='/var/run/am.pid')

    try:
        bus =  DefaultBus()

        log.info('answering machine starting (bus: %s)',
                bus.__class__.__name__)

        timer = TimerThread()
        timer.start()
        SpeechReactor.start()
        CallReactor.run()
    except:
        log.error('answering machine exception', exc_info=1)

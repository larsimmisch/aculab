#!/usr/bin/env python

import sys
import os
import getopt
import threading
import logging
import struct
import time
import smtplib
import email.Utils
from email import Encoders
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.MIMEAudio import MIMEAudio
import aculab
from aculab.error import AculabError
from aculab.callcontrol import Call, CallDispatcher
from aculab.speech import (SpeechChannel, SpeechDispatcher, Glue, PlayJob,
                           RecordJob)
from aculab.busses import DefaultBus
from aculab.timer import TimerThread

smtp_server = 'mail.ibp.de'
smtp_to = ['lars@ibp.de', 'claudia@ibp.de']
smtp_from = 'am@ibp.de'

root = '/usr/local/aculab/python'

# Modify this to change the time the answering machine waits before accepting
# the call
wait_accept = 20.0

# Accept calls only to these numbers
accept_called = ['41', '42']

# ripped from wave.py, which is just a teensy little bit too unflexible

WAVE_FORMAT_ALAW = 6
WAVE_FORMAT_MULAW = 7

def wav_header(data, format, nchannels = 1, sampwidth = 1,
               framerate = 8000):
    hdr = 'RIFF'
    nframes = len(data) / (nchannels * sampwidth)
    datalength = nframes * nchannels * sampwidth
    hdr = hdr + (struct.pack('<l4s4slhhllhh4sl',
                             36 + datalength, 'WAVE', 'fmt ', 16,
                             format, nchannels, framerate,
                             nchannels * framerate * sampwidth,
                             nchannels * sampwidth,
                             sampwidth * 8, 'data', datalength))

    return hdr

class AsyncEmail(threading.Thread):

    def __init__(self, file, call):
        super(self.__class__, self).__init__(name= 'email')
        self.file = file
        self.call = call
        self.setDaemon(1)

    def run(self):
        try:
            msg = MIMEBase('multipart', 'mixed')
            cli = self.call.details.originating_addr
            msg['Subject'] = 'Answering machine message from %s' % cli

            msg['Date'] = email.Utils.formatdate()
            msg['From'] = smtp_from
            msg['To'] = ', '.join(smtp_to)
            # this is not normally visible
            msg.preamble = 'This is a message in MIME format.\r\n'
            # Guarantees the message ends in a newline
            msg.epilogue = ''

            # attach small comment
            txt =  MIMEText('See audio (a-law) attachment')
            msg.attach(txt)

            d = self.file.read()
            att = MIMEAudio(wav_header(d, WAVE_FORMAT_ALAW) + d, 'x-wav',
                            name=time.strftime('%Y-%m-%d-%H-%M-%S') + '.wav')
            
            msg.attach(att)

            # close the file opened in the recording
            self.file.close()
            self.file = None

            # disconnect the call
            self.call.disconnect()
            self.call = None
        
            smtp = smtplib.SMTP(smtp_server)
            smtp.sendmail(smtp_from, smtp_to, msg.as_string(unixfrom=0))
            smtp.close()

            log.debug('answering machine mail sent from %s' % cli)
                        
        except:
            log.warn('answering machine email failed', exc_info=1)
            return

        log.info('sent answering machine message')

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
                self.call.disconnect()
        
class IncomingCallController(object):

    def ev_incoming_call_det(self, call, user_data):
        log.debug('%s called: %s calling: %s stream: %d timeslot: %d',
                  call.name, call.details.destination_addr,
                  call.details.originating_addr,
                  call.details.stream, call.details.ts)

        if call.details.destination_addr in accept_called:
            call.incoming_ringing()
            call.user_data = AnsweringMachine(self, module, call)
        
    def ev_call_connected(self, call, user_data):        
        user_data.start()
        
    def ev_remote_disconnect(self, call, user_data):
        user_data.speech.stop()

    def ev_idle(self, call, user_data):
        if user_data:
            user_data.close()
        call.user_data = None

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

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        super(self.__class__, self).ev_idle(call, user_data)
        call.openin()

def usage():
    print 'usage: am.py [-c <card>] [-p <port>] [-m <module>] [-d] [-t]'
    sys.exit(-2)

if __name__ == '__main__':

    card = 0
    port = 0
    module = 0
    controller = RepeatedIncomingCallController()
    daemon = False
    logfile = None
    test_run = None

    options, args = getopt.getopt(sys.argv[1:], 'p:sm:dt')

    for o, a in options:
        if o == '-c':
            card = int(a)
        if o == '-p':
            port = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-s':
            DefaultBus = SCBus()
        elif o == '-d':
            daemon = True
            logfile = '/var/log/am.log'
        elif o == '-t':
            test_run = True
        else:
            usage()

    log = aculab.defaultLogging(logging.DEBUG, logfile)

    call = Call(controller, card=card, port=port)

    if daemon:
        aculab.daemonize(pidfile='var/run/am.pid')

    timer = TimerThread()
    timer.start()
    SpeechDispatcher.start()
    CallDispatcher.run()


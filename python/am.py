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
from aculab.snapshot import Snapshot
from aculab.callcontrol import Call, CallDispatcher
from aculab.speech import SpeechChannel, SpeechDispatcher, Glue
from aculab.busses import DefaultBus

smtp_server = 'mail.basis-audionet.de'
smtp_to = 'martiniuc@basis-audionet.de'
smtp_from = 'am@ibp.de'

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
        threading.Thread.__init__(self, name= 'email')
        # rewind the file
        self.file = file
        self.call = call
        self.setDaemon(1)

    def run(self):
        try:
            msg = MIMEBase('multipart', 'mixed')
            msg['Subject'] = 'Answering machine message from %s' % \
                             self.call.details.originating_addr

            msg['Date'] = email.Utils.formatdate()
            msg['From'] = smtp_from
            msg['To'] = smtp_to
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

class IncomingCallController:

    def ev_incoming_call_det(self, call, user_data):
        log.debug('%s stream: %d timeslot: %d',
                  call.name, call.details.stream, call.details.ts)
        
        # The Prosody module that was globally selected.
        # Proper applications that handle multiple modules 
        # can be more clever here
        global module
        call.user_data = Glue(self, module)        
        call.accept()

    def ev_call_connected(self, call, user_data):        
        user_data.speech.play('greeting.al')
        
    def ev_remote_disconnect(self, call, user_data):
        call.disconnect()

    def ev_idle(self, call, user_data):
        user_data.close()
        call.user_data = None

    def play_done(self, channel, f, reason, position, user_data, job_data):
        t = os.tmpfile()
        channel.record(t, 90000, max_silence = 2000)

    def record_done(self, channel, f, reason, position, user_data, job_data):
        f.seek(0)        
        # f will be closed by AsyncEmail.run
        # the call will be hungup from AsyncEmail.run, too
        e = AsyncEmail(f, user_data.call)
        e.start()
        
    def digits_done(self, channel, user_data, job_data):
        pass
    
    def dtmf(self, channel, digit, user_data):
        print 'got DTMF:', digit

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call, user_data):
        call.openin()

def usage():
    print 'usage: am.py [-c <card>] [-p <port>] [-m <module>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':

    log = aculab.defaultLogging(logging.DEBUG)

    card = 0
    port = 0
    module = 0
    controller = IncomingCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:rsm:')

    for o, a in options:
        if o == '-c':
            card = int(a)
        if o == '-p':
            port = int(a)
        elif o == '-m':
            module = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        elif o == '-s':
            DefaultBus = SCBus()
        else:
            usage()

    snapshot = Snapshot()
    port = snapshot.call[card].ports[port].open.port_id

    call = Call(controller, port=port)

    SpeechDispatcher.start()
    CallDispatcher.run()

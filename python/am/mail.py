#!/usr/bin/env python

import sys
import logging
import time
import threading
import smtplib
import traceback
import email.Utils
from email import Encoders
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.MIMEAudio import MIMEAudio
from wav import *

smtp_server = 'mail.ibp.de'
smtp_to = ['lars@ibp.de', 'claudia@ibp.de']
smtp_from = 'am@ibp.de'

log = logging.getLogger('mail')

class AsyncEmail(threading.Thread):

    def __init__(self, file, call, cli = None):
        """Initialize a thread that will send an email with 'file' as an
        attachement. The 'call' will be disconnected when the email has been
        sent. 'cli' is overwritten unless 'call' is None; this is intended for
        testing."""
        
        super(self.__class__, self).__init__(name= 'email')
        self.file = file
        self.call = call
        if self.call:
            self.cli = call.details.originating_addr
        else:
            self.cli = cli

        self.setDaemon(1)

    def name_lookup(self, subject, txt):
        try:
            from vcard import (vcard_find, vcard_str, tel_normalize, tel_type)

            vc = vcard_find(self.cli)
            if vc:
                suffix = '(%s)' % self.cli
                for t in vc.tel_list:
                    if tel_normalize(self.cli) == tel_normalize(t.value):
                        suffix = '(%s: %s)' % (tel_type(t.params['TYPE']),
                                               self.cli)

                subject = 'Answering machine message from %s %s' \
                          % (vc.fn.value, suffix)
                txt = vcard_str(vc)
            else:
                subject = 'Answering machine message from %s' % self.cli
        except ImportError:
            pass
        except:
            log.warn('VCard lookup for CLI %s failed.', self.cli, exc_info=1)
            # Format exception
            ls = traceback.format_exception(sys.exc_type,
                                            sys.exc_value,
                                            sys.exc_traceback)

            txt = '%s\nAn error occurred looking up CLI: %s\n\n'% (txt, self.cli)
            for l in ls:
                txt = txt + l

        return (subject, txt)

    def run(self):
        try:
            subject = 'Answering machine message'
            txt = 'See audio attachment'
            
            if self.cli:
                subject = 'Answering machine message from %s' % self.cli
                subject, txt = self.name_lookup(subject, txt)

            msg = MIMEBase('multipart', 'mixed')
            msg['Subject'] = subject
            msg['Date'] = email.Utils.formatdate()
            msg['From'] = smtp_from
            msg['To'] = ', '.join(smtp_to)
            # this is not normally visible
            msg.preamble = 'This is a message in MIME format.\r\n'
            # Guarantees the message ends in a newline
            msg.epilogue = ''

            # attach text comment
            msg.attach(MIMEText(txt))

            if self.file:
                d = self.file.read()
                att = MIMEAudio(wav_header(d, WAVE_FORMAT_ALAW) + d, 'x-wav',
                                name=time.strftime('%Y-%m-%d-%H-%M-%S') + '.wav')
            
                msg.attach(att)

                # close the file opened in the recording
                self.file.close()
                self.file = None

            if self.call:
                # disconnect the call
                self.call.disconnect()
                self.call = None
        
            smtp = smtplib.SMTP(smtp_server)
            smtp.sendmail(smtp_from, smtp_to, msg.as_string(unixfrom=0))
            smtp.close()

        except:
            log.warn('answering machine email failed', exc_info=1)
            return

        log.info('answering machine mail sent from %s' % self.cli)

if __name__ == '__main__':

    def usage():
        print 'usage: mail.py [-t <to>] [<cli>]'
        sys.exit(2)

    sys.path.extend(['.', '..'])

    import getopt
    import aculab

    aculab.defaultLogging()
    
    # By default, only use the first email address
    smtp_to = smtp_to[:1]
    cli = '3172541'
    
    options, args = getopt.getopt(sys.argv[1:], 't:')

    for o, a in options:
        if o == '-t':
            smtp_to = [a]
        else:
            usage()

    if args:
        cli = args[0]

    a = AsyncEmail(None, None, cli)
    a.start()
    a.join()

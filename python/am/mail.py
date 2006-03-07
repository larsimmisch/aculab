import logging
import time
import threading
import smtplib
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

    def __init__(self, file, call):
        super(self.__class__, self).__init__(name= 'email')
        self.file = file
        self.call = call
        self.setDaemon(1)

    def run(self):
        try:
            subject = 'Answering machine message'
            txt = 'See audio attachment'
            
            cli = self.call.details.originating_addr
            if cli:
                try:
                    from vcard import (vcard_find, vcard_str, tel_normalize,
                                       tel_type)

                    vc = vcard_find(cli)
                    if vc:
                        suffix = '(%s)' % cli
                        for t in vc.tel:
                            if tel_normalize(cli) == tel_normalize(t.value):
                                suffix = '(%s: %s)' % (tel_type(t.params['TYPE']),
                                                       cli)
                    
                        subject = 'Answering machine message from %s %s' \
                                  % (vc.fn[0].value, suffix)
                        txt = vcard_str(vc)
                    else:
                        subject = 'Answering machine message from %s' % cli
                except ImportError:
                    pass
            
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

        except:
            log.warn('answering machine email failed', exc_info=1)
            return

        log.info('answering machine mail sent from %s' % cli)


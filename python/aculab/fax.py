import sys
import os
import time
import threading
import logging
import lowlevel
import names
from error import *

__all__ = ['FaxRxJob', 'FaxTxJob']

log = logging.getLogger('fax')

_fax_global_data = None

def fax_global_data():
    global _fax_global_data
    if not _fax_global_data:
        _fax_global_data = lowlevel.SMFAX_GLOBAL_DATA()
        rc = lowlevel.smfax_lib_init(_fax_global_data)
        if rc:
            raise AculabError(rc, 'smfax_lib_init')

    return _fax_global_data

class FaxJob:

    def __init__(self, channel, file, subscriber_id, job_data):
        self.channel = channel
        self.file = None
        self.filename = file
        self.job_data = job_data
        self.session = None
        self.logfile = None
        self.trace = None
        self.subscriber_id = subscriber_id

    def create_session(self, mode):
        self.mode = mode
        
        session = lowlevel.SMFAX_SESSION()
        session.channel = self.channel.channel
        # accept five percent bad lines
        session.user_options.max_percent_badlines = 0.10
        session.user_options.max_consec_badlines = 20
        session.user_options.ecm_continue_to_correct = 0
        session.user_options.drop_speed_on_ctc = 0
        session.user_options.fax_modem_fb = 0
        session.user_options.page_retries = 2
        session.user_options.fax_mode = mode
        session.fax_caps.v27ter = 1
        session.fax_caps.v29 = 1
        # There is currently no V.17 implementation available from Aculab
        # Todo: check if still valid
        session.fax_caps.v17 = 0
        # Todo: enable if possible
        session.fax_caps.ECM = 0
        session.fax_caps.MR2D = 1
        # Todo: enable if possible
        session.fax_caps.MMRT6 = 0
        session.fax_caps.polling_mode = 0
        session.fax_caps.Res200x200 = 1
        session.fax_caps.subscriber_id = self.subscriber_id
        session.global_data = fax_global_data()

        rc = lowlevel.smfax_create_session(session)
        if rc != lowlevel.kSMFaxStateMachineRunning:
            raise AculabError(rc, 'smfax_create_session')

        self.session = session

    def trace_on(self, level = 0x7fffffff):
        # open logfile for tracing
        rc, self.logfile = lowlevel.bfile()
        if rc:
            raise OSError(rc, 'bfile')

        fname = 'faxin.log'
        if self.mode == lowlevel.kSMFaxModeTransmitter:
            fname = 'faxout.log'

        rc = lowlevel.bfopen(self.logfile, fname, 'wtcb')
        if rc:
            raise OSError(rc, 'bfopen')

        self.trace = lowlevel.SMFAX_TRACE_PARMS()
        self.trace.log_file = self.logfile
        self.trace.fax_session = self.session
        self.trace.trace_level = level

        rc = lowlevel.smfax_trace_on(self.trace)
        if rc:
            raise AculabFAXError(rc, 'smfax_trace_on')
    
    def __del__(self):
        self.close()
        
    def close(self):
        if self.session:
            lowlevel.smfax_close_session(self.session)
            self.session = None

        if self.logfile:
            lowlevel.bfile_dtor(self.logfile)
            self.logfile = None

        if self.file:
            lowlevel.actiff_close(self.file)
            self.file = None

    def stop(self):
        if self.session:
            log.debug('%s fax stop', self.channel.name)

            rc = lowlevel.smfax_rude_interrupt(self.session)
            if rc:
                raise AculabFAXError(rc, 'smfax_rude_interrupt')

    def done(self, reason = AculabCompleted()):

        function = 'faxrx_done'
        if self.mode == lowlevel.kSMFaxModeTransmitter:
            function = 'faxtx_done'
        
        log.debug('%s %s(reason=\'%s\', exit_code=\'%s\')',
                  self.channel.name, function, reason,
                  names.fax_error_names[self.session.exit_error_code])

        self.close()
        channel = self.channel
        self.channel = None

        channel.job_done(self, function, reason)

class FaxRxJob(FaxJob, threading.Thread):
    
    def __init__(self, channel, file, subscriber_id = '', job_data = None):

        threading.Thread.__init__(self, name='faxrx ' + channel.name)

        FaxJob.__init__(self, channel, file, subscriber_id, job_data)
                
        self.file, rc = lowlevel.actiff_write_open(file, None)
        if rc:
            raise OSError(rc, 'actiff_write_open')
                
    def run(self):
        log.debug('%s faxrx(%s)',
                  self.channel.name, str(self.filename))

        self.create_session(lowlevel.kSMFaxModeReceiver)

        self.trace_on()

        neg = lowlevel.SMFAX_NEGOTIATE_PARMS()
        neg.fax_session = self.session
        neg.page_props = lowlevel.ACTIFF_PAGE_PROPERTIES()
        rc = lowlevel.smfax_rx_negotiate(neg)

        if rc != lowlevel.kSMFaxStateMachineRunning:
            self.done(AculabFAXError(rc, 'smfax_rx_negotiate'))
            return

        f = self.session.fax_caps
        log.debug('%s faxrx negotiated:\n' \
                  '  local: \'%s\', remote: \'%s\'\n'\
                  '  %d baud, resolution: %d',
                  self.channel.name,
                  f.remote_id, f.subscriber_id,
                  f.data_rate, f.polling_mode)

        while rc == lowlevel.kSMFaxStateMachineRunning:
            process = lowlevel.SMFAX_PAGE_PROCESS_PARMS()
            process.fax_session = self.session
            process.page_handle = lowlevel.ACTIFF_PAGE_HANDLE()
            rc = lowlevel.smfax_rx_page(process)

            log.debug('%s faxrx page received %s', self.channel.name,
                      names.fax_error_names[rc])

            access = lowlevel.SMFAX_PAGE_ACCESS_PARMS()
            access.fax_session = self.session
            access.actiff = self.file
            access.page_props = neg.page_props
            access.page_handle = process.page_handle
            rc2 = lowlevel.smfax_store_page(access)
            if rc2 != lowlevel.kSMFaxPageOK:
                self.stop()
                self.done(AculabFAXError(rc2, 'smfax_store_page'))
                return

            rc2 = lowlevel.smfax_close_page(process.page_handle)
            if rc2:
                self.stop()
                self.done(AculabFAXError(rc2, 'smfax_close_page'))
                return

        if rc == lowlevel.kSMFaxStateMachineTerminated:
            self.done()
        else:
            self.done(AculabFAXError(rc, 'FaxRxJob'))

class FaxTxJob(FaxJob, threading.Thread):
    
    def __init__(self, channel, file, subscriber_id = '', job_data = None):

        threading.Thread.__init__(self, name='faxtx ' + channel.name)

        FaxJob.__init__(self, channel, file, subscriber_id, job_data)
                
        self.file, rc = lowlevel.actiff_read_open(file)
        if rc:
            raise OSError(rc, 'actiff_read_open')

        # count pages in TIFF file
        self.page_count = 0
        while lowlevel.actiff_seek_page(self.file, self.page_count) == 0:
            self.page_count += 1
        
    def run(self):
        log.debug('%s faxtx(%s)',
                  self.channel.name, str(self.filename))

        self.create_session(lowlevel.kSMFaxModeTransmitter)

        self.trace_on()

        page_props = lowlevel.ACTIFF_PAGE_PROPERTIES()
        rc = lowlevel.actiff_page_properties(self.file, page_props)
        if rc:
            self.done(AculabFaxError(rc, 'actiff_page_properties'))
            return

        neg = lowlevel.SMFAX_NEGOTIATE_PARMS()
        neg.fax_session = self.session
        neg.page_props = page_props
        rc = lowlevel.smfax_tx_negotiate(neg)

        if rc != lowlevel.kSMFaxStateMachineRunning:
            self.done(AculabFAXError(rc, 'smfax_tx_negotiate'))
            return

        f = self.session.fax_caps
        log.debug('%s faxtx negotiated:\n' \
                  '  local: \'%s\', remote: \'%s\'\n'\
                  '  %d baud, resolution: %d',
                  self.channel.name,
                  f.remote_id, f.subscriber_id,
                  f.data_rate, f.polling_mode)

        for index in range(self.page_count):
            access = lowlevel.SMFAX_PAGE_ACCESS_PARMS()
            access.fax_session = self.session
            access.page_handle = lowlevel.ACTIFF_PAGE_HANDLE()
            access.page_index  = index
            access.page_props  = neg.page_props
            access.actiff      = self.file

            rc = lowlevel.smfax_need_conversion(access)
            if rc == lowlevel.kSMFaxTranscodeNeeded:
                # Load a page and convert it to suit the remote side
                rc = lowlevel.smfax_load_convert_page(access);
                log.debug('%s faxtx converting page', self.channel.name)
            elif rc ==  lowlevel.kSMFaxTranscodeNotNeeded:
                # Load a page without conversion
                rc = lowlevel.smfax_load_page(access)
            else:
                raise AculabFaxError(rc, 'smfax_need_conversion')

            process = lowlevel.SMFAX_PAGE_PROCESS_PARMS()
            process.fax_session = self.session
            process.page_handle = access.page_handle
            process.is_last_page = lowlevel.kSMFaxNotLastPage
            if index + 1 >= self.page_count:
                process.is_last_page = lowlevel.kSMFaxLastPage
            rc = lowlevel.smfax_tx_page(process)

            log.debug('%s faxtx page %d sent %s', self.channel.name, index + 1,
                      names.fax_error_names[rc])
            
            rc2 = lowlevel.smfax_close_page(process.page_handle)
            if rc2:
                self.stop()
                self.done(AculabFAXError(rc2, 'smfax_close_page'))
                return

        if rc == lowlevel.kSMFaxStateMachineRunning:
            self.done()
        else:
            self.done(AculabFAXError(rc, 'FaxRxJob'))

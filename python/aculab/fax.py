# Copyright (C) 2004-2007 Lars Immisch

"""FAX Job classes for the SpeechChannel."""

import sys
import os
import time
import threading
import logging
import lowlevel
from names import sm_error_names, fax_error_names
from error import AculabError, AculabFAXError
from util import translate_card, TiNG_version
from reactor import SpeechReactor
# The following are only needed for type comparisons
if TiNG_version[0] >= 2:
    from rtp import VMPtx, VMPtx, FMPtx, FMPrx
    from switching import TDMtx, TDMrx

__all__ = ['FaxRxJob', 'FaxTxJob']

log = logging.getLogger('fax')

_fax_global_data = None

def fax_global_data():
    global _fax_global_data
    if not _fax_global_data:
        _fax_global_data = lowlevel.SMFAX_GLOBAL_DATA()
        rc = lowlevel.smfax_lib_init(_fax_global_data)
        if rc:
            raise AculabFAXError(rc, 'smfax_lib_init')

    return _fax_global_data

class FaxJob:

    def __init__(self, channel, file, subscriber_id, vmp = (None, None)):
        """Initialize a FAX job.

        @param channel: The Prosody channel to send/receive the FAX on.
        @param file: a file name.
        @param subscriber_id: a string containing the alphanumerical subscriber
        id.
        @param vmp: a vmptx/vmprx pair if this is sent via RTP.
        """
        self.channel = channel
        self.file = None
        self.filename = file
        self.session = None
        self.logfile = None
        self.trace = None
        self.vmp = vmp
        self.subscriber_id = subscriber_id

    def create_session(self, mode):
        """Create the job (unfortunately called session by aculab)."""
        self.mode = mode

        session = lowlevel.SMFAX_SESSION()

        if TiNG_version[0] >= 2:
            session.module = self.channel.module.open.module_id
        else:
            session.module = self.channel.module

        session.channel = self.channel.channel
        session.vmptx = self.vmp[0].vmptx
        session.vmprx = self.vmp[1].vmprx
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
            raise AculabFAXError(rc, 'smfax_create_session')

        self.session = session

    def trace_on(self, level = 0x7fffffff):
        """Enable tracing for the FAX."""
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
        """Close the FAX job and aal open files."""
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
        """Stop the FAX job."""
        if self.session:
            log.debug('%s fax stop', self.channel.name)

            rc = lowlevel.smfax_rude_interrupt(self.session)
            if rc:
                raise AculabFAXError(rc, 'smfax_rude_interrupt')

    def done(self, reason = None):
        """Called internally when the job is complete or stopped."""

        function = 'faxrx_done'
        if self.mode == lowlevel.kSMFaxModeTransmitter:
            function = 'faxtx_done'
        
        log.debug('%s %s(reason=\'%s\', exit_code=\'%s\')',
                  self.channel.name, function, reason,
                  fax_error_names[self.session.exit_error_code])

        self.close()
        channel = self.channel
        self.channel = None

        channel.job_done(self, function, reason)

class FaxRxJob(FaxJob, threading.Thread):
    
    def __init__(self, channel, file, subscriber_id = '', vmp = (None, None)):
        """Prepare to receive a FAX.
        
        @param channel: The Prosody channel to send/receive the FAX on.
        @param file: a file name.
        @param subscriber_id: a string containing the alphanumerical subscriber
        id.
        @param vmp: a vmptx/vmprx pair if this is sent via RTP."""

        threading.Thread.__init__(self, name='faxrx ' + channel.name)

        FaxJob.__init__(self, channel, file, subscriber_id, vmp)
        
        self.file, rc = lowlevel.actiff_write_open(file, None)
        if rc:
            raise OSError(rc, 'actiff_write_open')
                
    def run(self):
        """Receive a FAX."""

        extra = ''
        if self.vmp[0] != None:
            extra = extra + 'tx: ' + self.vmp[0].name
        if self.vmp[1] != None:
            extra = extra + ' rx: ' + self.vmp[1].name
        
        log.debug('%s faxrx(%s, %s) %s',
                  self.channel.name, str(self.filename), self.subscriber_id,
                  extra)

        self.create_session(lowlevel.kSMFaxModeReceiver)

        # self.trace_on()

        neg = lowlevel.SMFAX_NEGOTIATE_PARMS()
        neg.fax_session = self.session
        neg.page_props = lowlevel.ACTIFF_PAGE_PROPERTIES()

        try:
            rc = lowlevel.smfax_negotiate(neg)
        except AttributeError:
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
                      fax_error_names[rc])

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
    
    def __init__(self, channel, file, subscriber_id = '',  vmp = (None, None)):
        """Prepare to receive a FAX.
        
        @param channel: The Prosody channel to send/receive the FAX on.
        @param file: a file name.
        @param subscriber_id: a string containing the alphanumerical subscriber
        id.
        @param vmp: a vmptx/vmprx pair if this is sent via RTP."""

        threading.Thread.__init__(self, name='faxtx ' + channel.name)

        FaxJob.__init__(self, channel, file, subscriber_id, vmp)
                
        self.file, rc = lowlevel.actiff_read_open(file)
        if rc:
            raise OSError(rc, 'actiff_read_open')

        # count pages in TIFF file
        self.page_count = 0
        while lowlevel.actiff_seek_page(self.file, self.page_count) == 0:
            self.page_count += 1
        
    def run(self):
        """Send a FAX."""

        extra = ''
        if self.vmp[0] != None:
            extra = extra + 'tx: ' + self.vmp[0].name
        if self.vmp[1] != None:
            extra = extra + ' rx: ' + self.vmp[1].name
        
        log.debug('%s faxtx(%s, %s) %s', self.channel.name, str(self.filename),
                  self.subscriber_id, extra)

        self.create_session(lowlevel.kSMFaxModeTransmitter)

        # self.trace_on()

        page_props = lowlevel.ACTIFF_PAGE_PROPERTIES()
        rc = lowlevel.actiff_page_properties(self.file, page_props)
        if rc:
            self.done(AculabFAXError(rc, 'actiff_page_properties'))
            return

        neg = lowlevel.SMFAX_NEGOTIATE_PARMS()
        neg.fax_session = self.session
        neg.page_props = page_props

        try:
            rc = lowlevel.smfax_negotiate(neg)
        except AttributeError:
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
                raise AculabFAXError(rc, 'smfax_need_conversion')

            process = lowlevel.SMFAX_PAGE_PROCESS_PARMS()
            process.fax_session = self.session
            process.page_handle = access.page_handle
            process.is_last_page = lowlevel.kSMFaxNotLastPage
            if index + 1 >= self.page_count:
                process.is_last_page = lowlevel.kSMFaxLastPage
            rc = lowlevel.smfax_tx_page(process)

            log.debug('%s faxtx page %d sent %s', self.channel.name, index + 1,
                      fax_error_names[rc])
            
            rc2 = lowlevel.smfax_close_page(process.page_handle)
            if rc2:
                self.stop()
                self.done(AculabFAXError(rc2, 'smfax_close_page'))
                return

        if rc == lowlevel.kSMFaxStateMachineRunning:
            self.done()
        else:
            self.done(AculabFAXError(rc, 'FaxRxJob'))

if TiNG_version[0] >= 2:
    class T38GWSession(threading.Thread):

        def __init__(self):
            threading.Thread.__init__(self, name='t38gwsession')

            session = lowlevel.SM_T38GW_SESSION_PARMS()

            rc = lowlevel.sm_t38gw_create_session(session)
            if rc:
                raise AculabFAXError(rc, 'sm_t38gw_session_create')

            self.session = session.session

        def stop(self):
            pstop = lowlevel.SM_T38GW_STOP_SESSION_PARMS()
            pstop.session = self.session

            rc = lowlevel.sw_t38gw_stop_session(pstop)
            if rc:
                raise AculabFAXError(rc, 'sm_t38gw_stop_session')

        def run(self):
            log.debug('t38gw-%x starting t38gw session', self.session)

            parms = lowlevel.SM_T38GW_WORKER_PARMS()
            parms.session = self.session

            rc = lowlevel.sm_t38gw_worker_fn(parms)
            if rc:
                log.error('t38gw-%x sm_t38gw_worker_fn failed: %s', self.session,
                          sm_error_names[rc])
            else:
                log.info('t38gw-%x sm_t38gw_worker_fn exited', self.session)

            rc = lowlevel.sm_t38gw_destroy_session(self.session)
            if rc:
                log.error('t38gw-%x sm_t38gw_destroy_session failed: %s',
                          self.session, sm_error_names[rc])

        def add(self, job):
            add_job = lowlevel.SM_T38GW_ADD_JOB_PARMS()
            add_job.session = self.session
            add_job.job = self.job

            rc = lowlevel.sm_t38gw_add_job(add_job)
            if rc:
                raise AculabFAXError(rc, 'sm_t38gw_add_job')

            log.debug('t38gw-%x started t38gw job)', self.session)


    class T38GWJob:

        def __init__(self, controller, local, remote, card = 0, module = 0,
                     modems = None, asn1 = 3, user_data = None,
                     reactor = SpeechReactor):
            """Create a fax job.

            @param controller: a controller that implements...
            @param local: a tuple (tx, rx) of either TDM, VMP or FMP for the local
            (sending) side.
            @param remote: a tuple (tx, rx) of either TDM, VMP or FMP for the
            remote (receiving side)
            @returns: a tSMT38GWJobId
            """

            if type(local) != tuple or type(remote) != tuple:
                raise ValueError('local and remote must be (tx, rx) tuples')

            if modems is None:
                modems = lowlevel.T38GW_MODEMTYPE_V29 | \
                         lowlevel.T38GW_MODEMTYPE_V27 | \
                         lowlevel.T38GW_MODEMTYPE_V17

            # Initialize early so that close can always be called.
            self.reactor = reactor
            self.fd = None
            self.job = None

            create = lowlevel.SM_T38GW_CREATE_JOB_PARMS()
            create.module = translate_card(card, module)[1].open.module_id
            create.asn1 = asn1
            create.modems = modems

            if type(local[0]) == VMPtx:
                if type(local[1]) != VMPrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.local_endpoint.type = lowlevel.kSMT38GWDeviceTypeT30VMP
                create.local_endpoint.T30VMP_EP.vmptx = local[0]
                create.local_endpoint.T30VMP_EP.vmprx = local[1]

            if type(local[0]) == TDMtx:
                if type(local[1]) != TDMrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.local_endpoint.type = lowlevel.kSMT38GWDeviceTypeT30TDM
                create.local_endpoint.T30TDM_EP.tdmtx = local[0]
                create.local_endpoint.T30TDM_EP.tdmrx = local[1] 

            if type(local[0]) == FMPtx:
                if type(local[1]) != FMPrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.local_endpoint.type = lowlevel.kSMT38GWDeviceTypeT38FMP
                create.local_endpoint.T38FMP_EP.fmptx = local[0]
                create.local_endpoint.T38FMP_EP.fmprx = local[1]

            if type(remote[0]) == VMPtx:
                if type(remote[1]) != VMPrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.remote_endpoint.type = lowlevel.kSMT38GWDeviceTypeT30VMP
                create.remote_endpoint.T30VMP_EP.vmptx = remote[0]
                create.remote_endpoint.T30VMP_EP.vmprx = remote[1]

            if type(remote[0]) == TDMtx:
                if type(remote[1]) != TDMrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.local.type = lowlevel.kSMT38GWDeviceTypeT30TDM
                create.local.T30TDM_EP.tdmtx = remote[0]
                create.local.T30TDM_EP.tdmrx = remote[1] 

            if type(remote[0]) == FMPtx:
                if type(remote[1]) != FMPrx:
                    raise ValueError('tx and rx must be of the same kind')

                create.remote_endpoint.type = lowlevel.kSMT38GWDeviceTypeT38FMP
                create.remote_endpoint.T38FMP_EP.fmptx = remote[0]
                create.remote_endpoint.T38FMP_EP.fmprx = remote[1]

            rc = lowlevel.sm_t38gw_create_job(create)
            if rc:
                raise AculabFAXError(rc, 'sm_t38gw_create_job')

            self.job = create.job
            self.fd = create.fd()
            self.reactor.add(self.fd, self.notify)

        def notify(self):
            status = lowlevel.SM_T38GW_JOB_STATUS_PARMS()
            status.job = self.job

            rc = lowlevel.sm_t38gw_job_status(status)
            if rc:
                # This shouldn't happen. This exception should shut down
                # the reactor (at least ours)
                raise AculabFAXError(rc, 'sm_t38gw_job_status')

            self.controller.t38gw_terminated(self)

        def close(self):
            if self.job:
                rc = lowlevel.sm_t38gw_destroy_job(self.job)
                self.job = None
                if rc:
                    raise AculabFAXError(rc, 'sm_t38gw_create_job')

            if self.fd:
                self.reactor.remove(self.fd)
                self.fd = None

        def stop(self):
            if self.job:
                abort = lowlevel.SM_T38GW_ABORT_PARMS()
                abort.job = self.job

                rc = lowlevel.sm_t38gw_abort_job(abort)
                if rc:
                    raise AculabFAXError(rc, 'sm_t38gw_abort_job')

import lowlevel
from error import AculabError
import pywintypes
import win32api

class SpeechChannel:
        
    def __init__(self, module = -1):

        if module != -1:
            alloc = lowlevel.SM_CHANNEL_ALLOC_PLACED_PARMS();

            alloc.type = lowlevel.kSMChannelTypeFullDuplex;
            alloc.module = module;

            rc = lowlevel.sm_channel_alloc_placed(alloc);
            if rc:
                raise AculabError(rc, 'sm_channel_alloc_placed');
        else:
            alloc = lowlevel.SM_CHANNEL_ALLOC_PARMS();

            alloc.type = lowlevel.kSMChannelTypeFullDuplex;

            rc = lowlevel.sm_channel_alloc(alloc);
            if rc:
                raise AculabError(rc, 'sm_channel_alloc');            

        self.channel = alloc.channel

        self.info = lowlevel.SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = lowlevel.sm_channel_info(self.info)
        if rc:
            raise AculabError(rc, 'sm_channel_info')

        listen_for = lowlevel.SM_LISTEN_FOR_PARMS()
        listen_for.channel = self.channel
        listen_for.tone_detection_mode = \
                                   lowlevel.kSMToneLenDetectionMinDuration64;
        listen_for.map_tones_to_digits = lowlevel.kSMDTMFToneSetDigitMapping;

        rc = lowlevel.sm_listen_for(listen_for)
        if rc:
            raise AculabError(rc, 'sm_listen_for')

        # initialise our events
        self.event_read = self.set_event(lowlevel.kSMEventTypeReadData)
        self.event_recog = self.set_event(lowlevel.kSMEventTypeRecog)
        self.event_write = self.set_event(lowlevel.kSMEventTypeWriteData);

    def __del__(self):
        lowlevel.smd_ev_free(self.event_read.handle)
        lowlevel.smd_ev_free(self.event_recog.handle)
        lowlevel.smd_ev_free(self.event_write.handle)

        rc = lowlevel.sm_channel_release(self.channel)
        if rc:
            raise AculabError(rc, 'sm_channel_release')

    def set_event(self, type):
        event = lowlevel.SM_CHANNEL_SET_EVENT_PARMS()

        event.channel = self.channel;
        event.issue_events = lowlevel.kSMChannelSpecificEvent;
        event.event_type = type;

        rc, event.handle = lowlevel.smd_ev_create(event.channel,
                                                  event.event_type,
                                                  event.issue_events)
        if rc:
            raise AculabError(rc, 'smd_ev_create')

        rc = lowlevel.sm_channel_set_event(event);
        if rc:
            smd_ev_free(event.handle);
            raise AculabError(rc, 'sm_channel_set_event')

        return pywintypes.HANDLE(event.handle);

    def listen_to(st, ts):
        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st = st
            input.ts = ts

            rc = lowlevel.sm_switch_channel_input(input)
            if (rc):
                raise AculabError(rc, 'sm_switch_channel_input')

        else:
            output = lowlevel.OUTPUT_PARMS()

            output.ost = self.info.ist		# sink
            output.ots = self.info.its
            output.mode = CONNECT_MODE
            output.ist = st
            output.its = ts
            
            rc = lowlevel.sw_set_output(self.info.card, output)
            if (rc):
                raise AculabError(rc, 'sw_set_output')


    def speak_to(st, ts):
        if self.info.card == -1:
            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st = st
            output.ts = ts

            rc = lowlevel.sm_switch_channel_output(output)
            if rc:
                return AculabError(rc, 'sm_switch_channel_output')            
        else:
            output = lowlevel.OUTPUT_PARMS()

            output.ost = st                     # sink
            output.ots = ts
            output.mode = lowlevel.CONNECT_MODE
            output.ist = self.info.ost			# source
            output.its = self.info.ots

            rc = lowlevel.sw_set_output(self.info.card, output)
            if rc:
                return AculabError(rc, 'sw_set_output')

    def disable_listener(st, ts):
        if self.info.card == -1:
            input = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st	  = -1	                # disconnect

            rc = lowlevel.sm_switch_channel_input(input)
            if rc:
                return AculabError(rc, 'sm_switch_channel_input')
        else:
            output = OUTPUT_PARMS()

            output.ost = st
            output.ots = ts
            output.mode = lowlevel.DISABLE_MODE
            rc = lowlevel.sw_set_output(self.info.card, output)
            if rc:
                raise AculabError(rc, 'sw_set_output')

    def disable_speaker(st, ts):
        if self.info.card == -1:

            output = lowlevel.SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st	   = -1                 # disconnect

            rc = lowlevel.sm_switch_channel_output(output);
            if (rc):
                AculabError(rc, 'sm_switch_channel_output')
        else:
            output = lowlevel.OUTPUT_PARMS()

            output.ost = st
            output.ots = ts
            output.mode = DISABLE_MODE
            rc = lowlevel.sw_set_output(self.info.card, output);
            if (rc):
                AculabError(rc, 'sw_set_output')

if __name__ == '__main__':
    c = SpeechChannel()
    del c

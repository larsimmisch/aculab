from aculab import *
import aculab_names as names
import pywintypes
import win32api

class AculabError:

    def __init__(self, function, rc):
        if rc in names.error.keys():
            self.value = rc
            self.desc = names.error[rc]
        else:
            self.value = 'unknown aculab error: ' + str(rc)
            
    def __str__(self):
        return self.desc

class ProsodyChannel:
        
    def __init__(self, module = -1):

        if module != -1:
            alloc = SM_CHANNEL_ALLOC_PLACED_PARMS();

            alloc.type = kSMChannelTypeFullDuplex;
            alloc.module = module;

            rc = sm_channel_alloc_placed(alloc);
            if rc:
                raise AculabError(rc);
        else:
            alloc = SM_CHANNEL_ALLOC_PARMS();

            alloc.type = kSMChannelTypeFullDuplex;

            rc = sm_channel_alloc(alloc);
            if rc:
                raise AculabError(rc);            

        self.channel = alloc.channel

        self.info = SM_CHANNEL_INFO_PARMS()
        self.info.channel = alloc.channel

        rc = sm_channel_info(self.info)
        if rc:
            raise AculabError(rc)

        listen_for = SM_LISTEN_FOR_PARMS()
        listen_for.channel = self.channel
        listen_for.tone_detection_mode = kSMToneLenDetectionMinDuration64;
        listen_for.map_tones_to_digits = kSMDTMFToneSetDigitMapping;

        rc = sm_listen_for(listen_for)
        if rc:
            raise AculabError(rc)

        # initialise our events
        self.event_read = self.set_event(kSMEventTypeReadData)
        self.event_recog = self.set_event(kSMEventTypeRecog)
        self.event_write = self.set_event(kSMEventTypeWriteData);

    def __del__(self):
        smd_ev_free(self.event_read.handle)
        smd_ev_free(self.event_recog.handle)
        smd_ev_free(self.event_write.handle)

        sm_channel_release(self.channel)

    def set_event(self, type):
        event = SM_CHANNEL_SET_EVENT_PARMS()

        event.channel = self.channel;
        event.issue_events = kSMChannelSpecificEvent;
        event.event_type = type;

        rc, event.handle = smd_ev_create(event.channel, event.event_type,
                                         event.issue_events)
        if rc:
            raise AculabError(rc)

        rc = sm_channel_set_event(event);
        if rc:
            smd_ev_free(event.handle);
            raise AculabError(rc)

        return pywintypes.HANDLE(event.handle);

    def listen_to(st, ts):
        if self.info.card == -1:
            input = SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st = st
            input.ts = ts

            rc = sm_switch_channel_input(input)
        else:
            output = OUTPUT_PARMS()

            output.ost = self.info.ist		# sink
            output.ots = self.info.its
            output.mode = CONNECT_MODE
            output.ist = st
            output.its = ts
            
            rc = sw_set_output(self.info.card, output)

        if (rc):
            raise AculabError(rc)


    def speak_to(st, ts):
        if self.info.card == -1:
            output = SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st = st
            output.ts = ts

            rc = sm_switch_channel_output(output)
        else:
            output = OUTPUT_PARMS()

            output.ost = st                     # sink
            output.ots = ts
            output.mode = CONNECT_MODE
            output.ist = self.info.ost			# source
            output.its = self.info.ots

            rc = sw_set_output(self.info.card, output)

            if rc:
                return AculabError(rc)


    def disable_listener(st, ts):
        if self.info.card == -1:
            input = SM_SWITCH_CHANNEL_PARMS()

            input.channel = self.channel
            input.st	  = -1	                # disconnect

            rc = sm_switch_channel_input(input)
        else:
            output = OUTPUT_PARMS()

            output.ost = st
            output.ots = ts
            output.mode = DISABLE_MODE
            rc = sw_set_output(self.info.card, output)

        if rc:
            raise AculabError(rc)

    def disable_speaker(st, ts):
        if self.info.card == -1:

            output = SM_SWITCH_CHANNEL_PARMS()

            output.channel = self.channel
            output.st	   = -1                 # disconnect

            rc = sm_switch_channel_output(output);
        else:
            output = OUTPUT_PARMS()

            output.ost = st
            output.ots = ts
            output.mode = DISABLE_MODE
            rc = sw_set_output(self.info.card, output);

            if (rc):
                AculabError(rc)

c = ProsodyChannel()

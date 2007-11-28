#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import logging
import aculab
import aculab.lowlevel as lowlevel
from aculab import defaultLogging
from aculab.error import AculabError
from aculab.speech import SpeechChannel
from aculab.reactor import SpeechReactor
from aculab.switching import connect

class DTMFLoopController:

    def dtmf(self, channel, digit, user_data):
        pass

    def record_done(self, channel, file, reason, size, user_data):
        pass

    def play_done(self, channel, reason, f, duration, user_data):
        raise StopIteration
                
    def digits_done(self, channel, reason, user_data):
        # Play a CNG
        channel.tone(23, 1.0)

    def tone_done(self, channel, reason, user_data):
        # Give the CNG detector some time
        channel.silence(1.0)

    def silence_done(self, channel, reason, duration, user_data):
        raise StopIteration

if __name__ == '__main__':

    log = defaultLogging(logging.DEBUG)

    parser = aculab.defaultOptions(
        description='Detect DTMF and CNG on two loopback channels.')

    parser.add_option('-l', '--lendetect', action='store_const', dest='mode',
                      default=lowlevel.kSMToneDetectionMinDuration64,
                      const=lowlevel.kSMToneLenDetectionMinDuration64,
                      help='Use kSMToneLenDetectionMinDuration64 for the' \
                      'tone detection mode.')

    parser.add_option('-f', '--file-name', 
                      help='Play FILE instead of sending 0123456789*#')

    options, args = parser.parse_args()

    controller = DTMFLoopController()

    channels = [SpeechChannel(controller, options.card, options.module),
                SpeechChannel(controller, options.card, options.module)]

    connection = connect(channels[0], channels[1])

    channels[0].listen_for('dtmf/fax', options.mode)
    
    channels[0].record('dtmf.al', max_silence = 1.0)
    if options.file_name:
        channels[1].play(options.file_name)
    else:
        channels[1].digits('0123456789*#')

    SpeechReactor.run()

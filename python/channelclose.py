#!/usr/bin/env python

import time
from aculab.error import AculabError
from aculab.callcontrol import Call, CallDispatcher
from aculab.speech import SpeechChannel, SpeechDispatcher

SpeechDispatcher.start()

for i in range(20):
    speech = SpeechChannel(controller, 0)
    time.sleep(0.1)
    speech.close()
    speech = None
        
time.sleep(5)


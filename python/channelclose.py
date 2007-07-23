#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import time
from aculab.error import AculabError
from aculab.callcontrol import Call
from aculab.speech import SpeechChannel
from aculab.reactor import CallReactor, SpeechReactor

SpeechReactor.start()

for i in range(20):
    speech = SpeechChannel(controller, 0)
    time.sleep(0.1)
    speech.close()
    speech = None
        
time.sleep(5)


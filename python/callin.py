import sys
import re
import aculab
import __main__

# build a map of EV_* constants
event_names = {}
event_pattern = re.compile(r'EV_[A-Z_]+')

for k in aculab.__dict__.keys():
    if event_pattern.match(k):
        event_names[aculab.__dict__[k]] = k.lower()

inparms = aculab.in_xparms()
inparms.ts = -1

aculab.call_openin(inparms)
    
handle = inparms.handle

event = aculab.state_xparms()

def ev_ext_facility(handle):
    pass

def ev_incoming_call_det(handle):
    aculab.call_accept(handle)

def ev_call_connected(handle):
    pass

def ev_remote_disconnect(handle):
    aculab.call_disconnect(handle)

def ev_idle(handle):
    cause = aculab.cause_xparms()
    cause.handle = handle
    aculab.call_release(cause)
    sys.exit(0)

last_event = None
while 1:
    event.handle = handle
    event.timeout = 1000

    rc = aculab.call_event(event)
    # call the event handler
    if last_event != event.state:
        print event_names[event.state]
        __main__.__dict__[event_names[event.state]](handle)
        last_event = event.state


import sys
import getopt
import aculab
import aculab_names as names
import __main__

def usage():
    print 'callin.py [-p <port>]'
    
port = 0

options, args = getopt.getopt(sys.argv[1:], 'p:')

for o, a in options:
    if o == '-p':
        port = int(a)
    else:
        usage()

inparms = aculab.IN_XPARMS()
inparms.net = port
inparms.ts = -1

aculab.call_openin(inparms)
    
handle = inparms.handle

event = aculab.STATE_XPARMS()

def ev_ext_facility(handle):
    pass

def ev_incoming_call_det(handle):
    aculab.call_accept(handle)

def ev_call_connected(handle):
    pass

def ev_remote_disconnect(handle):
    aculab.call_disconnect(handle)

def ev_idle(handle):
    cause = aculab.CAUSE_XPARMS()
    cause.handle = handle
    aculab.call_release(cause)

    inparms = aculab.IN_XPARMS()
    inparms.net = port
    inparms.ts = -1

    aculab.call_openin(inparms)
    
    handle = inparms.handle


last_event = None
while 1:
    event.handle = handle
    event.timeout = 1000

    rc = aculab.call_event(event)
    # call the event handler
    if last_event != event.state:
        print names.event[event.state].lower()
        __main__.__dict__[names.event[event.state].lower()](handle)
        last_event = event.state


#!/usr/bin/env python

from aculab.snapshot import Snapshot

snapshot = Snapshot()

print '%d call control cards' % len(snapshot.call)
for c in snapshot.call:
    print '    %s: %d ports' % (c.card.serial_no, len(c.ports))

print '%d prosody card' % len(snapshot.prosody)
for c in snapshot.prosody:
    print '    %s: %d modules' % (c.card.serial_no, len(c.modules))

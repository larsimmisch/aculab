#!/usr/bin/env python

# Copyright (C) 2004-2007 Lars Immisch

from pprint import PrettyPrinter
from aculab.snapshot import Snapshot

snapshot = Snapshot()

print '%d call control cards' % len(snapshot.call)
for c in snapshot.call:
    print '    %s: %d ports' % (c.card.serial_no, len(c.ports))

print '%d prosody card' % len(snapshot.prosody)
for c in snapshot.prosody:
    print '    %s: %d modules' % (c.card.serial_no, len(c.modules))

pp = PrettyPrinter()

snapshot.pprint()

import lowlevel
from error import AculabError

class CTBus:

    def allocate(self):
        return self.slots.pop(0)

    def free(self, slot):
        self.slots.append(slot)

    def listen_to(self, switch, sink, source):
        "sink and source are tuples of timeslots"
        output = lowlevel.OUTPUT_PARMS()
        output.ost = sink[0]
        output.ots = sink[1]
        output.mode = lowlevel.CONNECT_MODE
        output.ist = source[0]
        output.its = source[1]

        print "%d: %d:%d := %d:%d" % (switch, sink[0], sink[1],
                                      source[0], source[1])

        rc = lowlevel.sw_set_output(switch, output)
        if rc:
            raise AculabError(rc, 'sw_set_output')

class MVIP(CTBus):

    def __init__(self):
        self.slots = []
        for st in range(16):
            for ts in range(32):
                self.slots.append((st, ts))

    def invert(self, slot):
        if slot[0] < 8:
            return (slot[0] + 8, slot[1])
        else:
            return (slot[0] - 8, slot[1])

class SCBus(CTBus):

    def __init__(self):
        self.slots = []
        for ts in range(1024):
            self.slots.append((24, ts))

class H100(CTBus):

    def __init__(self):
        self.slots = []
        for st in range(32):
            for ts in range(128):
                self.slots.append((st, ts))

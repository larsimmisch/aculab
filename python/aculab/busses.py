class CTBus:

    def allocate(self):
        return self.slots.pop(0)

    def free(self, slot):
        self.slots.append(slot)

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

class SCBus:

    def __init__(self):
        self.slots = []
        for ts in range(1024):
            self.slots.append((24, ts))

class H100:

    def __init__(self):
        self.slots = []
        for st in range(32):
            for ts in range(128):
                self.slots.append((st, ts))

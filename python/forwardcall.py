import sys
import getopt
from aculab.error import AculabError
from aculab.callcontrol import *

class ForwardCallController:

    def __init__(self):
        self.incall = None
        self.outcall = None

    def ev_incoming_call_det(self, call):
        self.incall = call
        self.outcall = Call(self, port, incall.details.destination_addr, 2)

    def ev_remote_disconnect(self, call):
        if call == self.incall:
            self.outcall.disconnect()
        else:
            self.incall.disconnect()

        call.disconnect()

    def ev_idle(self, call):
        if call == self.incall:
            self.outcall.disconnect()
        else:
            self.incall.disconnect()

def usage():
    print 'forwardcall.py [-p <port>]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    controller = ForwardCallController()

    options, args = getopt.getopt(sys.argv[1:], 'p:r')

    for o, a in options:
        if o == '-p':
            port = int(a)
        else:
            usage()

    c = Call(controller, port)

    dispatcher.run()

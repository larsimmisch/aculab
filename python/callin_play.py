import sys
import getopt
import threading
from aculab.error import AculabError
from aculab.callcontrol import Call, CallEventDispatcher
from aculab.speech import SpeechChannel, SpeechEventDispatcher
from aculab.busses import autodetect

class IncomingCallController:

    def __init__(self):
        self.mutex = threading.Lock()

    def ev_incoming_call_det(self, call):
        print hex(call.handle), 'stream: %d timeslot: %d' \
              % (call.details.stream, call.details.ts)

        call.accept()

    def ev_call_connected(self, call):
        call.connections = [ call.listen_to(call.timeslots[0]),
                             call.speech.speak_to(call.timeslots[0]),
                             call.speak_to(call.timeslots[1]),
                             call.speech.listen_to(call.timeslots[1]) ]
        
        call.speech.play('c:/tmp/startrek.al')
        # call.speech.digits('12345')
        # call.speech.record('c:/tmp/recording.al', 90000)
        
    def ev_remote_disconnect(self, call):
        call.speech.stop()
        call.connections = None
        call.disconnect()

    def play_done(self, channel, position, user_data):
        print 'play done. position:', position

    def record_done(self, channel, how, position, user_data):
        print 'record done. position: %d how: %d' % (position, how)

    def digits_done(self, channel, user_data):
        print 'digits done'

    def dtmf(self, channel, digit):
        print 'got DTMF:', digit

class RepeatedIncomingCallController(IncomingCallController):

    def ev_idle(self, call):
        call.restart()

def usage():
    print 'usage: callin.py [-p <port>] [-r]'
    sys.exit(-2)

if __name__ == '__main__':
    port = 0
    controller = IncomingCallController()

    bus = autodetect()
    print bus

    options, args = getopt.getopt(sys.argv[1:], 'p:rs')

    for o, a in options:
        if o == '-p':
            port = int(a)
        elif o == '-r':
            controller = RepeatedIncomingCallController()
        elif o == '-s':
            bus = SCBus()
        else:
            usage()

    if not bus:
        bus = H100()

    speechdispatcher = SpeechEventDispatcher()
    calldispatcher = CallEventDispatcher()

    call = Call(controller, calldispatcher, port)
    call.speech = SpeechChannel(controller, speechdispatcher)
    call.timeslots = (bus.allocate(), bus.allocate())

    speechdispatcher.start()
    calldispatcher.run()

#!/usr/bin/env python

import unittest
from aculab.error import AculabError, AculabSpeechError
from aculab.sdp import SDP

class ErrorTest(unittest.TestCase):
    """Check formatting and name resolution of Aculab errors."""

    def raise_error(self, e):
        raise e

    def testAErrorBasic(self):
        'Raise an Aculab error'
        self.assertRaises(AculabError, self.raise_error, AculabError(-2))

    def testAErrorDesc(self):
        'AculabError: check description (no function name)'
        try:
            raise AculabError(-2)
        except AculabError, e:
            self.failUnless(e.desc == 'unknown failed: ERR_HANDLE')

    def testAErrorDescF(self):
        'AculabError: check description (with function name)'
        try:
            raise AculabError(-2, 'foo')
        except AculabError, e:
            self.failUnless(e.desc == 'foo failed: ERR_HANDLE')

    def testAErrorDescFN(self):
        '''AculabError: check description (with function and name)'''
        try:
            raise AculabError(-2, 'foo', 'cc-1234')
        except AculabError, e:
            self.failUnless(e.desc == 'cc-1234 foo failed: ERR_HANDLE')

    def testAErrorValue(self):
        'AculabError: check the value'
        try:
            raise AculabError(-2)
        except AculabError, e:
            self.failUnless(e.value == -2)

    def testSErrorDescFN(self):
        '''AculabSpeechError: check description (with function and name)'''
        try:
            raise AculabSpeechError(-116, 'foo', 'sc-4321')
        except AculabSpeechError, e:
            self.failUnless(
                e.desc == 'sc-4321 foo failed: ERR_SM_WRONG_CHANNEL_STATE')

class SDPTest(unittest.TestCase):
    """Test SDP parsing and generation."""

    def testAParseSDP(self):
        '''SDP: parse and read the media address for audio.'''

        s = '''v=0\r
o=root 6194 6194 IN IP4 192.168.11.224\r
s=pyaculab\r
c=IN IP4 192.168.11.224\r
t=0 0\r
m=audio 8092 RTP/AVP 0 8 101\r
a=rtpmap:0 PCMU/8000/1\r
a=rtpmap:8 PCMA/8000/1\r
a=rtpmap:101 telephone-event/8000'''

        sdp = SDP(s)
        self.failUnless(sdp.getAddress('audio') == ('192.168.11.224', 8092))

    def testBParseSDP(self):
        '''SDP: parse and read the address (with invalid line endings).'''

        s = '''v=0
o=root 6194 6194 IN IP4 192.168.11.224
s=pyaculab
c=IN IP4 192.168.11.224
t=0 0
m=audio 8092 RTP/AVP 0 8 101
a=rtpmap:0 PCMU/8000/1
a=rtpmap:8 PCMA/8000/1
a=rtpmap:101 telephone-event/8000'''

        sdp = SDP(s)
        self.failUnless(sdp.getAddress('audio') == ('192.168.11.224', 8092))

    def testCParseT38(self):
        '''SDP: parse T38 and check the address and the T38FaxVersion.'''
        
        t38 = '''v=0
o=THOR 0 0 IN IP4 192.168.11.111
s=session
c=IN IP4 192.168.11.111
b=CT:116
t=0 0
m=image 10026 udptl t38
a=T38FaxVersion:3
a=T38maxBitRate:9600
a=T38FaxFillBitRemoval:0
a=T38FaxTranscodingMMR:0
a=T38FaxTranscodingJBIG:0
a=T38FaxRateManagement:transferredTCF
a=T38FaxMaxBuffer:284
a=T38FaxMaxDatagram:128
a=T38FaxUdpEC:t38UDPRedundancy'''

        sdp = SDP(t38)
        self.failUnless(sdp.getAddress('image') == ('192.168.11.111', 10026))
        self.failUnless(sdp.getMediaDescription('image')._a['T38FaxVersion']
                        == ['3'])

if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python

# Copyright (C) 2004 Anthony Baxter
# Copyright (C) 2004 Jamey Hicks

# Nicked from shtoom

"""SDP, aka Session Description Protocol, as described in RFC 2327.

Nicked from shtoom. 

This is a quick example on how to parse an SDP and access various fields:

>>> s = '''v=0\r
... o=root 6194 6194 IN IP4 192.168.11.224\r
... s=pyaculab\r
... c=IN IP4 192.168.11.224\r
... t=0 0\r
... m=audio 8092 RTP/AVP 0 8 101\r
... a=rtpmap:0 PCMU/8000/1\r
... a=rtpmap:8 PCMA/8000/1\r
... a=rtpmap:101 telephone-event/8000\r
... '''

>>> sdp = SDP(s)
>>> sdp.getAddress('audio')
('192.168.11.224', 8092)
>>> sdp.getMediaDescription('audio').rtpmap   
{0: ('0 PCMU/8000/1', <AudioPTMarker PCMU(0)/8000/1 at b715918c>),
8: ('8 PCMA/8000/1', <AudioPTMarker PCMA(8)/8000/1 at b715926c>),
101: ('101 telephone-event/8000',
<PTMarker telephone-event(dynamic)/8000/None at b715954c>)}
"""

from util import OrderedDict

class PTMarker:
    "A marker of a particular payload type"
    media = None

    def __init__(self, name, pt=None, clock=8000, params=1, fmtp=None):
        self.name = name
        self.pt = pt
        self.clock = clock
        self.params = params
        self.fmtp = fmtp

    def __repr__(self):
        if self.pt is None:
            pt = 'dynamic'
        else:
            pt = str(self.pt)
        cname = self.__class__.__name__
        return "<%s %s(%s)/%s/%s at %x>"%(cname, self.name, pt,
                                          self.clock, self.params, id(self))

class AudioPTMarker(PTMarker):
    "An audio payload type"
    media = 'audio'

class VideoPTMarker(PTMarker):
    "A video payload type"
    media = 'video'

PT_PCMU =       AudioPTMarker('PCMU',    clock=8000,  params=1, pt=0)
PT_GSM =        AudioPTMarker('GSM',     clock=8000,  params=1, pt=3)
# G723 is actually G.723.1, but is the same as G.723. XXX test against cisco
PT_G723 =       AudioPTMarker('G723',    clock=8000,  params=1, pt=4)
PT_DVI4 =       AudioPTMarker('DVI4',    clock=8000,  params=1, pt=5)
PT_DVI4_16K =   AudioPTMarker('DVI4',    clock=16000, params=1, pt=6)
PT_LPC =        AudioPTMarker('LPC',     clock=8000,  params=1, pt=7)
PT_PCMA =       AudioPTMarker('PCMA',    clock=8000,  params=1, pt=8)
PT_G722 =       AudioPTMarker('G722',    clock=8000,  params=1, pt=9)
PT_L16_STEREO = AudioPTMarker('L16',     clock=44100, params=2, pt=10)
PT_L16 =        AudioPTMarker('L16',     clock=44100, params=1, pt=11)
PT_QCELP =      AudioPTMarker('QCELP',   clock=8000,  params=1, pt=12)
PT_CN =         AudioPTMarker('CN',      clock=8000,  params=1, pt=13)
PT_G728 =       AudioPTMarker('G728',    clock=8000,  params=1, pt=15)
PT_DVI4_11K =   AudioPTMarker('DVI4',    clock=11025, params=1, pt=16)
PT_DVI4_22K =   AudioPTMarker('DVI4',    clock=22050, params=1, pt=17)
PT_G729 =       AudioPTMarker('G729',    clock=8000,  params=1, pt=18)
PT_xCN =        AudioPTMarker('xCN',     clock=8000,  params=1, pt=19)
PT_SPEEX =      AudioPTMarker('speex',   clock=8000,  params=1)
PT_SPEEX_16K =  AudioPTMarker('speex',   clock=16000, params=1)
PT_G726_40 =    AudioPTMarker('G726-40', clock=8000,  params=1)
# Deprecated - gone from RFC3551
PT_1016 =       AudioPTMarker('1016', clock=8000,  params=1, pt=1)
# aka G723-40 (5 bit data)
PT_G726_40 =    AudioPTMarker('G726-40', clock=8000,  params=1)
# G726-32 aka G721-32 (4 bit data)
PT_G726_32 =    AudioPTMarker('G726-32', clock=8000,  params=1)
# Deprecated spelling for G726-32 - gone from RFC3551
PT_G721 =       AudioPTMarker('G721', clock=8000,  params=1, pt=2)
# G726-24 aka G723-24 (3 bit data)
PT_G726_24 =    AudioPTMarker('G726-24', clock=8000,  params=1)
PT_G726_16 =    AudioPTMarker('G726-16', clock=8000,  params=1)
PT_G729D =      AudioPTMarker('G729D',   clock=8000,  params=1)
PT_G729E =      AudioPTMarker('G729E',   clock=8000,  params=1)
PT_GSM_EFR =    AudioPTMarker('GSM-EFR', clock=8000,  params=1)
PT_ILBC =       AudioPTMarker('iLBC',    clock=8000,  params=1)
#PT_L8 =         AudioPTMarker('L8',      clock=None,  params=1)
#PT_RED =        AudioPTMarker('RED',     clock=8000,  params=1)
#PT_VDVI =       AudioPTMarker('VDVI',    clock=None,  params=1)
PT_NTE =        PTMarker('telephone-event', clock=8000, params=None,
                        fmtp='0-16')
PT_CELB =       VideoPTMarker('CelB', clock=90000, pt=25)
PT_JPEG =       VideoPTMarker('JPEG', clock=90000, pt=26)
PT_NV =         VideoPTMarker('nv',   clock=90000, pt=28)
PT_H261 =       VideoPTMarker('H261', clock=90000, pt=31)
PT_MPV =        VideoPTMarker('MPV',  clock=90000, pt=32)
PT_MP2T =       VideoPTMarker('MP2T', clock=90000, pt=33)
PT_H263 =       VideoPTMarker('H263', clock=90000, pt=34)

RTPDict = {}
all = globals()
for key,val in all.items():
    if isinstance(val, PTMarker):
        # By name
        RTPDict[key] = val
        # By object
        if val.pt is not None:
            RTPDict[val] = val.pt
        # By PT
        if val.pt is not None:
            RTPDict[val.pt] = val
        # By name/clock/param
        RTPDict[(val.name.lower(),val.clock,val.params or 1)] = val

del all, key, val

def get(obj,typechar,optional=0):
    return obj._d.get(typechar)

def getA(obj, subkey):
    return obj._a.get(subkey)

def parse_generic(obj, k, text):
    obj._d.setdefault(k, []).append(text)

def unparse_generic(obj, k):
    if obj._d.has_key(k):
        return obj._d[k]
    else:
        return []

def parse_singleton(obj, k, text):
    obj._d[k] = text

def unparse_singleton(obj, k):
    if obj._d.has_key(k):
        return [obj._d[k]]
    else:
        return []

def parse_o(obj, o, value):
    if value:
        l = value.split()
        if len(l) != 6:
            raise ValueError("SDP: wrong # fields in o=`%s'"%value)
        ( obj._o_username, obj._o_sessid, obj._o_version,
            obj._o_nettype, obj._o_addrfamily, obj._o_ipaddr ) = tuple(l)

def unparse_o(obj, o):
    return ['%s %s %s %s %s %s' % ( obj._o_username, obj._o_sessid,
                                    obj._o_version, obj._o_nettype,
                                    obj._o_addrfamily, obj._o_ipaddr )]

def parse_a(obj, a, text):
    words = text.split(':', 1)
    if len(words) > 1:
        # I don't know what is happening here, but I got a traceback here
        # because 'words' was too long before the ,1 was added.  The value was:
        # ['alt', '1 1 ', ' 55A94DDE 98A2400C *ip address elided* 6086']
        # Adding the ,1 seems to fix it but I don't know why. -glyph
        attr, attrvalue = words
    else:
        attr, attrvalue = text, None
    if attr == 'rtpmap':
        payload,info = attrvalue.split(' ')
        entry = rtpmap2canonical(int(payload), attrvalue)
        try:
            fmt = RTPDict[entry]
        except KeyError:
            name,clock,params = entry
            fmt = PTMarker(name, None, clock, params)
        obj.rtpmap[int(payload)] = (attrvalue, fmt)
        obj._a.setdefault(attr, OrderedDict())[int(payload)] = attrvalue
    else:
        obj._a.setdefault(attr, []).append(attrvalue)

def unparse_a(obj, k):
    out = []
    for (a,vs) in obj._a.items():
        if isinstance(vs, OrderedDict):
            vs = vs.values()
        for v in vs:
            if v:
                out.append('%s:%s' % (a, v))
            else:
                out.append(a)
    return out

def parse_c(obj, c, text):
    words = text.split(' ')
    (obj.nettype, obj.addrfamily, obj.ipaddr) = words

def unparse_c(obj, c):
    return ['%s %s %s' % (obj.nettype, obj.addrfamily, obj.ipaddr)]

def parse_m(obj, m, value):
    if value:
        els = value.split()
        (obj.media, port, obj.transport) = els[:3]
        obj.setFormats(els[3:])
        obj.port = int(port)

def unparse_m(obj, m):
    return ['%s %s %s %s' % (obj.media, str(obj.port), obj.transport,
                            ' '.join(obj.formats))]

parsers = [
    ('v', 1, parse_singleton, unparse_singleton),
    ('o', 1, parse_o, unparse_o),
    ('s', 1, parse_singleton, unparse_singleton),
    ('i', 0, parse_generic, unparse_generic),
    ('u', 0, parse_generic, unparse_generic),
    ('e', 0, parse_generic, unparse_generic),
    ('p', 0, parse_generic, unparse_generic),
    ('c', 0, parse_c, unparse_c),
    ('b', 0, parse_generic, unparse_generic),
    ('t', 0, parse_singleton, unparse_singleton),
    ('r', 0, parse_generic, unparse_generic),
    ('k', 0, parse_generic, unparse_generic),
    ('a', 0, parse_a, unparse_a)
    ]

mdparsers = [
    ('m', 0, parse_m, unparse_m),
    ('i', 0, parse_generic, unparse_generic),
    ('c', 0, parse_generic, unparse_generic),
    ('b', 0, parse_generic, unparse_generic),
    ('k', 0, parse_generic, unparse_generic),
    ('a', 0, parse_a, unparse_a)
]

parser = {}
unparser = {}
mdparser = {}
mdunparser = {}
for (key, required, parseFcn, unparseFcn) in parsers:
    parser[key] = parseFcn
    unparser[key] = unparseFcn
for (key, required, parseFcn, unparseFcn) in mdparsers:
    mdparser[key] = parseFcn
    mdunparser[key] = unparseFcn
del key,required,parseFcn,unparseFcn

class MediaDescription:
    "The MediaDescription encapsulates all of the SDP media descriptions"
    def __init__(self, text=None):
        self.nettype = 'IN'
        self.addrfamily = 'IP4'
        self.ipaddr = None
        self.port = None
        self.transport = None
        self.formats = []
        self._d = {}
        self._a = {}
        self.rtpmap = OrderedDict()
        self.media = 'audio'
        self.transport = 'RTP/AVP'
        self.keyManagement = None
        if text:
            parse_m(self, 'm', text)

    def setFormats(self, formats):
        if self.media in ( 'audio', 'video'):
            for pt in formats:
                pt = int(pt)
                if pt < 97:
                    try:
                        PT = RTPDict[pt]
                    except KeyError:
                        # We don't know this one - hopefully there's an
                        # a=rtpmap entry for it.
                        continue
                    self.addRtpMap(PT)
                    # XXX the above line is unbound local variable error if
                    # not RTPDict.has_key(pt) --Zooko 2004-09-29
        self.formats = formats

    def setMedia(self, media):
        """Set the media type.

        @param media: must be 'audio' or 'video'
        """
        self.media = media
        
    def setTransport(self, transport):
        self.transport = transport
        
    def setServerIP(self, l):
        self.ipaddr = l
        
    def setLocalPort(self, l):
        self.port = l

    def setKeyManagement(self, km):
        parse_a(self, 'keymgmt', km)

    def clearRtpMap(self):
        self.rtpmap = OrderedDict()

    def addRtpMap(self, fmt):
        if fmt.pt is None:
            pts = self.rtpmap.keys()
            pts.sort()
            if pts and pts[-1] > 100:
                payload = pts[-1] + 1
            else:
                payload = 101
        else:
            payload = fmt.pt
        rtpmap = "%d %s/%d%s%s"%(payload, fmt.name, fmt.clock,
                                 ((fmt.params and '/') or ""),
                                 fmt.params or "")
        self.rtpmap[int(payload)] = (rtpmap, fmt)
        self._a.setdefault('rtpmap', OrderedDict())[payload] = rtpmap
        self.formats.append(str(payload))

    def intersect(self, other):
        """See RFC 3264."""
        
        map1 = self.rtpmap
        d1 = {}
        for code,(e,fmt) in map1.items():
            d1[rtpmap2canonical(code,e)] = e
        map2 = other.rtpmap
        outmap = OrderedDict()
        # XXX quadratic - make rtpmap an ordereddict
        for code, (e, fmt) in map2.items():
            canon = rtpmap2canonical(code,e)
            if d1.has_key(canon):
                outmap[code] = (e, fmt)
        self.rtpmap = outmap
        self.formats = [ str(x) for x in self.rtpmap.keys() ]
        self._a['rtpmap'] = OrderedDict([ (code,e) for
                                          (code, (e, fmt)) in outmap.items() ])

class SDP:
    """An SDP body, parsed for easy access."""
    
    def __init__(self, text=None):
        from time import time
        self._id = None
        self._d = {'v': '0', 't': '0 0', 's': 'pyaculab'}
        self._a = OrderedDict()
        self.mediaDescriptions = []
        # XXX Use the username preference
        self._o_username = 'root'
        self._o_sessid = self._o_version = str(int(time()%1000 * 100))
        self._o_nettype = self.nettype = 'IN'
        self._o_addrfamily = self.addrfamily = 'IP4'
        self._o_ipaddr = self.ipaddr = None
        self.port = None
        if text:
            if isinstance(text, list):
                self.parse(text)
            elif isinstance(text, str):
                if text.find('\r\n') > -1:
                    self.parse(text.split('\r\n'))
                else:
                    self.parse(text.split('\n'))
            else:
                raise ValueError('text must be list of strings or string')
            self.assertSanity()
        else:
            # new SDP
            pass

    def name(self):
        return self._sessionName

    def info(self):
        return self._sessionInfo

    def version(self):
        return self._o_version

    def id(self):
        if not self._id:
            self._id = (self._o_username, self._o_sessid, self.nettype,
                        self.addrfamily, self.ipaddr)
        return self._id

    def parse(self, lines):
        md = None
        for line in lines:
            elts = line.split('=')
            if len(elts) != 2:
                continue
            (k,v) = elts
            try:
                if k == 'm':
                    md = MediaDescription(v)
                    self.mediaDescriptions.append(md)
                elif md:
                    mdparser[k](md, k, v)
                else:
                    parser[k](self, k, v)
            except KeyError:
                raise ValueError, line            

    def get(self, typechar, option=None):
        if option is None:
            return get(self, typechar)
        elif typechar is 'a':
            return getA(self, option)
        else:
            raise ValueError, "only know about suboptions for 'a' so far"

    def setServerIP(self, l):
        self._o_ipaddr = self.ipaddr = l

    def addSessionAttribute(self, attrname, attrval):
        if not isinstance(attrval, (list, tuple)):
            attrval = (attrval,)
        self._a[attrname] = attrval

    def addMediaDescription(self, md):
        self.mediaDescriptions.append(md)

    def removeMediaDescription(self, md):
        self.mediaDescriptions.remove(md)

    def getMediaDescription(self, media):
        for md in self.mediaDescriptions:
            if md.media == media:
                return md
        return None

    def hasMediaDescriptions(self):
        return bool(len(self.mediaDescriptions))

    def show(self):
        """Return a textual representation of the SDP suitable for use as a
        SIP body."""
        out = []
        for (k, req, p, u) in parsers:
            for l in u(self, k):
                out.append('%s=%s' % (k, l))
        for md in self.mediaDescriptions:
            for (k, req, p, u) in mdparsers:
                for l in u(md, k):
                    out.append('%s=%s' % (k, l))
        out.append('')
        s = '\r\n'.join(out)
        return s

    def intersect(self, other):
        """See RFC 3264."""
        mds = self.mediaDescriptions
        self.mediaDescriptions = []
        for md in mds:
            omd = None
            for o in other.mediaDescriptions:
                if md.media == o.media:
                    omd = o
                    break
            if omd:
                md.intersect(omd)
                self.mediaDescriptions.append(md)

    def getAddress(self, media):
        """Return a tuple (ipaddr, port)"""
        
        md = self.getMediaDescription(media)
        if not md:
            return None

        if not md.ipaddr:
            return (self.ipaddr, md.port)

        return (md.ipaddr, md.port)

    def assertSanity(self):
        pass

    def __str__(self):
        """Return a textual representation of the SDP suitable for use as a
        SIP body."""
        
        return self.show()

def ntp2delta(ticks):
    return (ticks - 220898800)

def rtpmap2canonical(code, entry):
    if not isinstance(code, int):
        raise ValueError(code)
    if code < 96:
        return code
    else:
        ocode,desc = entry.split(' ',1)
        desc = desc.split('/')
        if len(desc) == 2:
            desc.append('1') # default channels
        name,rate,channels = desc
        return (name.lower(),int(rate),int(channels))

if __name__ == '__main__':

    md = MediaDescription()
    md.setLocalPort(8092)
    md.addRtpMap(PT_PCMU)
    md.addRtpMap(PT_PCMA)
    md.addRtpMap(PT_NTE)
    

    sdp = SDP()
    sdp.setServerIP('192.168.11.224')
    sdp.addMediaDescription(md)
    
    s = str(sdp)

    print s

    sdp = SDP(s)
    print sdp.getMediaDescription('audio').rtpmap
    print sdp.getAddress('audio')

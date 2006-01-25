# ripped from wave.py, which is just a teensy little bit too unflexible

import struct

WAVE_FORMAT_ALAW = 6
WAVE_FORMAT_MULAW = 7

def wav_header(data, format, nchannels = 1, sampwidth = 1,
               framerate = 8000):
    hdr = 'RIFF'
    nframes = len(data) / (nchannels * sampwidth)
    datalength = nframes * nchannels * sampwidth
    hdr = hdr + (struct.pack('<l4s4slhhllhh4sl',
                             36 + datalength, 'WAVE', 'fmt ', 16,
                             format, nchannels, framerate,
                             nchannels * framerate * sampwidth,
                             nchannels * sampwidth,
                             sampwidth * 8, 'data', datalength))

    return hdr

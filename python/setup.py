#!/usr/bin/env python

import os

if os.name == 'nt':
    define_macros = [('WIN32', None)]
    include_dirs = ['../include']
    lib_dirs = []
    libs = ['advapi32']
    sources = ['acu_wrap.c',
               '../src/clnt.c',
               '../src/cllib.c',
               '../src/common.c',
               '../src/swnt.c',
               '../src/swlib.c',
               '../src/smnt.c',
               '../src/smlib.c',
               '../src/smbesp.c',
               '../src/smfwcaps.c' ]

elif os.name == 'unix':
    dtk = '../dtk111'
    define_macros = [('UNIX_SYSTEM', None),
                     ('SM_POLL_UNIX', None)]
    includes = [dtk + '/call/include',
                dtk + '/switch/include',
                dtk + '/speech/include']
    lib_dirs = [dtk + '/call/lib',
                dtk + '/switch/lib',
                dtk + '/speech/lib'],
    libs = ['mvcl', 'mvsw', 'mvsm']
    sources = ["acu.i"]

from distutils.core import setup,Extension

setup (name = "aculab",
	   version = "1.3",
	   description = "Aculab Python wrapper",
	   author = "Lars Immisch",
	   author_email = "lars@ibp.de",
	   ext_modules = [Extension("aculab._lowlevel", sources,
                                include_dirs = include_dirs,
                                library_dirs = lib_dirs,
                                libraries = libs,
                                define_macros = define_macros)],
       packages = ["aculab"])


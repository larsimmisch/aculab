#!/usr/bin/env python

dtk = '../dtk111'

from distutils.core import setup,Extension

setup (name = "aculab",
	   version = "1.2",
	   description = "Aculab Python wrapper",
	   author = "Lars Immisch",
	   author_email = "lars@ibp.de",
	   ext_modules = [Extension("aculab._lowlevel", ["acu.i"],
                                include_dirs = [dtk + '/call/include',
                                                dtk + '/switch/include',
                                                dtk + '/speech/include'],
                                library_dirs = [dtk + '/call/lib',
                                                dtk + '/switch/lib',
                                                dtk + '/speech/lib'],
                                libraries = ['mvcl', 'mvsw', 'mvsm'],
                                define_macros = [('UNIX_SYSTEM', None),
                                                 ('SM_POLL_UNIX', None)])],
       packages = ["aculab"])


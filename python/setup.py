#!/usr/bin/env python

from distutils.core import setup,Extension

setup (name = "aculab",
	   version = "1.0",
	   description = "Aculab Python wrapper",
	   author = "Lars Immisch",
	   author_email = "lars@ibp.de",
	   ext_modules = [Extension("aculab.lowlevelc", ["acu_wrap.c",
                                                     "../src/clnt.c",
                                                     "../src/cllib.c",
                                                     "../src/common.c",
                                                     "../src/swnt.c",
                                                     "../src/swlib.c",
                                                     "../src/smnt.c",
                                                     "../src/smlib.c",
                                                     "../src/smbesp.c",
                                                     "../src/smfwcaps.c"],
								include_dirs = ['../include'],
                                define_macros = [('WIN32', None)])],
	   packages = ["aculab"])


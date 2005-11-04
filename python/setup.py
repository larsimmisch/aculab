#!/usr/bin/env python

import os

if os.name == 'nt':
    raise RuntimeError('Windows not supported yet')
elif os.name == 'posix':
    dtk = os.getenv('ACULAB_ROOT')
    fax = '/ProsodyLibraries/Group3fax_LINUX_V6_rel321/API'
    define_macros = [('ACU_LINUX', None),
                     ('SM_POLL_UNIX', None),
                     ('TiNGTYPE_LINUX', None),
                     ('TiNG_USE_V6', None)]
    include_dirs = [dtk + '/include',
                    dtk + '/ting/include',
                    dtk + fax + '/include' ]
    extra_objects = [dtk + '/ting/libutil/gen-LINUX_V6/aculog.o',
                     dtk + '/ting/libutil/gen-LINUX_V6/vseprintf.o',   
                     dtk + '/ting/libutil/gen-LINUX_V6/bfile.o',   
                     dtk + '/ting/libutil/gen-LINUX_V6/bfopen.o',
                     dtk + fax + '/lib/actiff.o',
                     dtk + fax + '/lib/faxlib.o' ]
    lib_dirs = [dtk + '/lib']
    libs = ['acu_cl', 'acu_res', 'TiNG', 'acu_common']
    sources = ["acu.i"]
    swig_opts = ['-modern', '-new_repr'] + \
                ['-D%s' % d[0] for d in define_macros] + \
                ['-I%s' % i for i in include_dirs] \

from distutils.core import setup,Extension

setup (name = "aculab",
	   version = "2.0",
	   description = "Aculab Python wrapper",
	   author = "Lars Immisch",
	   author_email = "lars@ibp.de",
	   ext_modules = [Extension("aculab._lowlevel", sources,
                                include_dirs = include_dirs,
                                library_dirs = lib_dirs,
                                libraries = libs,
                                extra_objects = extra_objects,
                                define_macros = define_macros,
                                swig_opts = swig_opts)],
       packages = ["aculab"])


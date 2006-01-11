#!/usr/bin/env python

import os

def macroify(m):
    if m[1]:
        return '-D%s=s' % m
    else:
        return '-D%s' % m[0]

extra_objects = None

if os.name == 'nt':
    raise RuntimeError('Windows not supported yet')
elif os.name == 'posix':
    dtk = os.getenv('ACULAB_ROOT')
    if not dtk:
        raise ValueError('ACULAB_ROOT is not defined')

    # crude detection of V5 vs v6
    if os.path.exists(dtk + '/include/cl_lib.h'):
        # Version 6
        version = '6.0'
        fax = '/ProsodyLibraries/Group3fax_LINUX_V6_rel321/API'
        if not os.path.exists(dtk + fax):
            fax = None
                      
        define_macros = [('ACU_LINUX', None),
                         ('SM_POLL_UNIX', None),
                         ('TiNGTYPE_LINUX', None),
                         ('TiNG_USE_V6', None)]
        include_dirs = [dtk + '/include',
                        dtk + '/ting/include']

        extra_objects = [dtk + '/ting/libutil/gen-LINUX_V6/aculog.o',
                         dtk + '/ting/libutil/gen-LINUX_V6/vseprintf.o',   
                         dtk + '/ting/libutil/gen-LINUX_V6/bfile.o',   
                         dtk + '/ting/libutil/gen-LINUX_V6/bfopen.o']
        if fax:
            define_macros.append(('HAVE_FAX', None))
            include_dirs.append(dtk + fax + '/include')
            extra_objs = extra_objs + [dtk + fax + '/lib/actiff.o',
                                       dtk + fax + '/lib/faxlib.o']
            
        lib_dirs = [dtk + '/lib']
        libs = ['acu_cl', 'acu_res', 'TiNG', 'acu_common', 'stdc++']
        sources = ["lowlevel.i"]
    else:
        # Version 5
        version = '5.0' 
        define_macros = [('ACU_LINUX', None),
                         ('SM_POLL_UNIX', None)]

        include_dirs = [dtk + '/call/include',
                        dtk + '/switch/include',
                        dtk + '/speech/include']

        lib_dirs = [dtk + '/call/lib',
                    dtk + '/switch/lib',
                    dtk + '/speech/lib']
        libs = ['mvcl', 'mvsw', 'mvsm']
        sources = ["lowlevel.i"]
    
swig_opts = ['-modern', '-new_repr'] + \
            [macroify(d) for d in define_macros] + \
            ['-I%s' % i for i in include_dirs]

from distutils.core import setup,Extension

setup (name = "aculab",
	   version = version,
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


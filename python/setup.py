#!/usr/bin/env python

# Copyright (C) 2002-2007 Lars Immisch

import os
import xml.sax
import xml.sax.handler
from distutils.core import setup,Extension
from distutils.command.build_ext import build_ext
from distutils.dep_util import newer
from distutils import log
import shutil

def svnversion():
    cmd = os.popen('svnversion -n .')
    revision = cmd.read()
    cmd.close()

    return revision

def macroify(m):
    if m[1]:
        return '-D%s=s' % m
    else:
        return '-D%s' % m[0]

class FindStruct(xml.sax.handler.ContentHandler):
    '''Helper class to find all structs that have a size member from
    the a SWIG generated XML file.

    This is pretty ugly, but it does the job (and I am no XML expert).'''

    def __init__(self, file, exclude = []):
        self.in_class = 0
        self.in_typescope = 0
        self.in_cdecl = 0
        self.candidate = None
        self.locator = None
        self.file = file
        self.exclude = exclude

    #Overridden DocumentHandler methods
    def setDocumentLocator(self, locator):
        #If the parser supports location info it invokes this event
        #before any other methods in the DocumentHandler interface
        self.locator = locator

    def startElement(self, name, attrs):
        if name == 'class':
            self.in_class = self.in_class + 1
        elif name == 'typescope':
            self.in_typescope = self.in_typescope + 1
        elif name == 'cdecl':
            self.in_cdecl = self.in_cdecl + 1

        if self.in_class == 1 and \
               name == 'attribute' and attrs['name'] == 'sym_name':
            if self.in_typescope == 0 and self.in_cdecl == 0:
                self.candidate = attrs['value']
            if self.in_cdecl:
                if self.candidate and attrs['value'] == 'size':
                    if not self.candidate in self.exclude:
                        self.file.write('SIZED_STRUCT(%s)\n' % self.candidate)

    def endElement(self, name):
        if name == 'class':
            self.candidate = None
            self.in_class = self.in_class - 1
        elif name == 'typescope':
            self.in_typescope = self.in_typescope - 1
        elif name == 'cdecl':
            self.in_cdecl = self.in_cdecl - 1

class build_ext_swig_in_package(build_ext):
    
    def pre_swig_hook(self, sources, ext):
        """Extra hook to build cl_lib.h2 and sized_struct.i"""

        # crude detection of V5 vs v6

        cl_lib = os.path.join(dtk, 'include', 'cl_lib.h')
        if os.path.exists(cl_lib):
            # This is V6

            # Create patched versions for cl_lib.h and acu_type.h
            
            # To generate a patch, (for example cl_lib.patch), copy the
            # original cl_lib.h to cl_lib.h2, edit it, and then do:
            # diff -u $(DTK)/include/cl_lib.h cl_lib.h2 > cl_lib.patch

            if newer('cl_lib.patch', 'cl_lib.h2'):
                self.spawn(['patch', '-o', 'cl_lib.h2', cl_lib,
                            'cl_lib.patch'])
                
                self.spawn(['patch', '-o', 'acu_type.h2',
                            os.path.join(dtk, 'include', 'acu_type.h'),
                            'acu_type.patch'])

            swig = self.swig or self.find_swig()
            swig_cmd = [swig, '-xml', '-xmllite']
            swig_cmd.extend(self.swig_opts)

            if newer('lowlevel.i', 'sized_struct.i'):
                # Do not override commandline arguments
                if not self.swig_opts:
                    for o in ext.swig_opts:
                        # More ugly hacks.
                        # Remove Python specific swig args
                        if not o in ['-modern', '-new_repr']:
                            swig_cmd.append(o)

                self.spawn(swig_cmd + ['-o', 'lowlevel.xml', 'lowlevel.i'])

                of = open('sized_struct.i', 'w')
                parser = xml.sax.make_parser()
                handler = FindStruct(of, u'ACU_SNAPSHOT_PARMS')

                parser.setContentHandler(handler)
                parser.parse('lowlevel.xml')
                of.close()
        else:
            # Create patched version for smosintf.h
            if newer('smosintf.patch', 'smosintf.h2'):
                self.spawn(['patch', '-o', 'smosintf.h2',
                            os.path.join(dtk, 'speech', 'include',
                                         'smosintf.h'),
                            'smosintf.patch'])


    def swig_sources(self, sources, extension):
        """swig these days generates a shadow module, but distutils doesn't
        know about it.

        This (rather crude) build_ext subclass copies the shadow python
        module into their package, assuming standard package layout.
        
        It also defines a pre_swig_hook that is called immediately before
        swig is called.
        
        It doesn't support more than one .i file per extension.
        """
        self.pre_swig_hook(sources, extension)
        
        sources = build_ext.swig_sources(self, sources, extension)
        package_parts = extension.name.split('.')
        module = package_parts.pop()
        if module[0] != '_':
            log.warn('SWIG extensions must start with an underscore')
            return
        # strip underscore
        module = module[1:]
        if package_parts:
            log.warn("cp %s %s", module +'.py', os.path.join(*package_parts))
            shutil.copy(module +'.py', os.path.join(*package_parts))

        return sources

extra_objects = []

if os.name == 'nt':
    import _winreg
    try:
        # This is for versions Call 5.x/Prosody 1.y
        
        h = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                            'SOFTWARE\\Aculab\\acusetup')
        dtk = str(_winreg.QueryValueEx(h, 'BaseDirectory')[0])
        h.Close()
        dtk = os.path.split(dtk.rstrip('\\'))[0]
        dtk = os.path.join(dtk, 'API')

        define_macros = []
        lib_dirs = []
        libs = []

        include_dirs = [os.path.join(dtk, 'Call', 'include'),
                        os.path.join(dtk, 'Switch', 'include'),
                        os.path.join(dtk, 'Speech', 'include')]

        sources = [os.path.join(dtk, 'Call', 'lib', 'cllib.c'),
                   os.path.join(dtk, 'Call', 'lib', 'clnt.c'),
                   os.path.join(dtk, 'Call', 'lib', 'common.c'),
                   os.path.join(dtk, 'Switch', 'lib', 'swlib.c'),
                   os.path.join(dtk, 'Switch', 'lib', 'swnt.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smbesp.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smclib.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smdc.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smfwcaps.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smlib.c'),
                   os.path.join(dtk, 'Speech', 'lib', 'smnt.c'),
                   "lowlevel.i"]
    except WindowsError:
        
        # This is for Call 6.x/Prosody 2.y
        dtk = os.getenv('ACULAB_ROOT')
        if not dtk:
            raise ValueError('ACULAB_ROOT is not defined')

        fax = '/ProsodyLibraries/Group3Fax/API'
        if not os.path.exists(dtk + fax):
            fax = None

        t38gw = '/ProsodyLibraries/T38_Gateway'
        if not os.path.exists(dtk + t38gw):
            t38gw = None

        define_macros = [('_WIN32', None),
                         ('WIN32', None),
                         ('TiNGTYPE_WINNT', None),
                         ('TiNG_USE_V6', None)]

        include_dirs = [dtk + '/include',
                        dtk + '/TiNG/pubdoc/gen',
                        dtk + '/TiNG/apilib',
                        dtk + '/TiNG/apilib/WINNT',
                        dtk + '/TiNG/include' ]

        lib_dirs = [dtk + '/lib']
        libs = ['cl_lib', 'res_lib', 'sw_lib', 'rmsm', 'TiNG', 'ws2_32']
        sources = ['lowlevel.i']

elif os.name == 'posix':
    dtk = os.getenv('ACULAB_ROOT')
    if not dtk:
        raise ValueError('ACULAB_ROOT is not defined')

    # crude detection of V5 vs v6
    if os.path.exists(dtk + '/include/cl_lib.h'):
        fax = '/ProsodyLibraries/Group3Fax/API'
        if not os.path.exists(dtk + fax):
            fax = None

        t38gw = '/ProsodyLibraries/T38_Gateway'
        if not os.path.exists(dtk + t38gw):
            t38gw = None

        define_macros = [('ACU_LINUX', None),
                         ('SM_POLL_UNIX', None),
                         ('TiNGTYPE_LINUX', None),
                         ('TiNG_USE_V6', None)]

        include_dirs = [dtk + '/include',
                        dtk + '/TiNG/pubdoc/gen',
                        dtk + '/TiNG/apilib',
                        dtk + '/TiNG/apilib/POSIX',
                        dtk + '/TiNG/include' ]

        lib_dirs = [dtk + '/lib']
        libs = ['acu_cl', 'acu_res', 'acu_sw', 'acu_rmsm', 'acu_common',
                'TiNG', 'stdc++']
        sources = ["lowlevel.i"]

        if fax:
            define_macros.append(('HAVE_FAX', None))
            include_dirs.append(dtk + fax + '/include')
            lib_dirs.append(dtk + fax + '/lib')
            libs.extend(['faxlib', 'actiff', 'fontconfig'])
            extra_objects = [dtk + '/ting/libutil/gen-LINUX_V6/aculog.o',
                             dtk + '/ting/libutil/gen-LINUX_V6/vseprintf.o',   
                             dtk + '/ting/libutil/gen-LINUX_V6/bfile.o',   
                             dtk + '/ting/libutil/gen-LINUX_V6/bfopen.o']

            if t38gw:
                define_macros.append(('HAVE_T38GW', None))
                include_dirs.append(dtk + t38gw + '/include')
                lib_dirs.append(dtk + t38gw + '/lib')
                libs.append('smt38gwlib')

    else:
        define_macros = [('UNIX_SYSTEM', None),
                         ('ACU_LINUX', None),
                         ('SM_POLL_UNIX', None)]

        include_dirs = [dtk + '/call/include',
                        dtk + '/switch/include',
                        dtk + '/speech/include']

        lib_dirs = [dtk + '/call/lib',
                    dtk + '/switch/lib',
                    dtk + '/speech/lib']
        libs = ['mvcl', 'mvsw', 'mvsm']
        sources = ["lowlevel.i"]
    
swig_opts = ['-modern', '-new_repr', '-DTiNG_USE_UNDECORATED_NAMES'] + \
            [macroify(d) for d in define_macros] + \
            ['-I%s' % i for i in include_dirs]

setup(name = "pyAculab",
      version = svnversion(),
      description = "Aculab Python wrappers",
      author = "Lars Immisch",
      author_email = "lars@ibp.de",
      url = "http://svn.ibp.de/projects/aculab",
      cmdclass = { 'build_ext' : build_ext_swig_in_package },
      ext_modules = [Extension("aculab._lowlevel", sources,
                               include_dirs = include_dirs,
                               library_dirs = lib_dirs,
                               libraries = libs,
                               extra_objects = extra_objects,
                               define_macros = define_macros,
                               swig_opts = swig_opts)],
      packages = ["aculab"])


#!/usr/bin/env python

import sys
import getopt
import os
from distutils.file_util import copy_file
from distutils.dir_util import mkpath
import distutils.sysconfig as ds
from distutils.errors import DistutilsFileError
import compileall

def usage():
    print "disthelper.py -i | -l | -L | -v | <file>+"
    sys.exit(2)

# copied from distutils.dir_utils. 

def copy_tree (src, dst,
               preserve_mode=1,
               preserve_times=1,
               preserve_symlinks=0,
               update=0,
               verbose=0,
               dry_run=0,
               ignore=[]):

    """Copy an entire directory tree 'src' to a new location 'dst'.  Both
       'src' and 'dst' must be directory names.  If 'src' is not a
       directory, raise DistutilsFileError.  If 'dst' does not exist, it is
       created with 'mkpath()'.  The end result of the copy is that every
       file in 'src' is copied to 'dst', and directories under 'src' are
       recursively copied to 'dst'.  Return the list of files that were
       copied or might have been copied, using their output name.  The
       return value is unaffected by 'update' or 'dry_run': it is simply
       the list of all files under 'src', with the names changed to be
       under 'dst'.

       'preserve_mode' and 'preserve_times' are the same as for
       'copy_file'; note that they only apply to regular files, not to
       directories.  If 'preserve_symlinks' is true, symlinks will be
       copied as symlinks (on platforms that support them!); otherwise
       (the default), the destination of the symlink will be copied.
       'update' and 'verbose' are the same as for 'copy_file'.

       'ignore' will ignore all files or subdirectories listed
       (at any level)"""

    from distutils.file_util import copy_file

    if not dry_run and not os.path.isdir(src):
        raise DistutilsFileError, \
              "cannot copy tree '%s': not a directory" % src
    try:
        names = os.listdir(src)
    except os.error, (errno, errstr):
        if dry_run:
            names = []
        else:
            raise DistutilsFileError, \
                  "error listing files in '%s': %s" % (src, errstr)

    if not dry_run:
        mkpath(dst)

    outputs = []

    for n in names:
        if not n in ignore:
            src_name = os.path.join(src, n)
            dst_name = os.path.join(dst, n)

            if preserve_symlinks and os.path.islink(src_name):
                link_dest = os.readlink(src_name)
                log.info("linking %s -> %s", dst_name, link_dest)
                if not dry_run:
                    os.symlink(link_dest, dst_name)
                outputs.append(dst_name)

            elif os.path.isdir(src_name):
                outputs.extend(
                    copy_tree(src_name, dst_name, preserve_mode,
                              preserve_times, preserve_symlinks, update,
                              dry_run=dry_run, ignore=ignore))
            else:
                copy_file(src_name, dst_name, preserve_mode,
                          preserve_times, update, dry_run=dry_run)
                outputs.append(dst_name)

    return outputs

# copy_tree ()

if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ilLvh?')
    except getopt.GetoptError:
        usage()

    for o, a in opts:
        if o == '-i':
            print ds.get_python_inc()
            sys.exit(0)
        if o == '-l':
            print ds.get_python_lib()
            sys.exit(0)
        if o == '-L':
            lib_dir = ds.get_python_lib(plat_specific=1, standard_lib=1)
            print os.path.join(lib_dir, "config")
            sys.exit(0)
        if o == '-v':
            print ds.get_python_version()
            sys.exit(0)
        else:
            usage()

    if len(args) < 1:
        usage()

    python_lib = ds.get_python_lib()

    for f in sys.argv[1:]:
        print 'installing %s in %s' % (f, python_lib)

        try:
            if os.path.isdir(f):
                dest = os.path.join(python_lib, f)
                copy_tree(f, dest, update=True)
            else:
                df.copy_file(f, python_lib, update=True, ignore='.svn')
                
        except DistutilsFileError, e:
            print e
            sys.exit(1)

    compileall.compile_dir(python_lib, quiet=True)
        

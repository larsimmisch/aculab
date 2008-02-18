# Copyright (C) 2003-2007 Lars Immisch

"""Event driven, MVC inspired Python wrapper around the Aculab API."""

import optparse
import logging
import logging.handlers

__all__ = ['_lowlevel', 'lowlevel', 'names', 'error', 'util',
           'switching', 'callcontrol', 'speech', 'sip', 'sdp', 'rtp', 'fax'
           'daemonize', 'defaultLogging']

# From: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012

def daemonize(stdout='/dev/null', stderr=None, stdin='/dev/null',
              pidfile=None):
    """ This forks the current process into a daemon.
    
    The C{stdin}, C{stdout}, and C{stderr} arguments are file names that
    will be opened and used to replace the standard file descriptors
    in C{sys.stdin}, C{sys.stdout}, and C{sys.stderr}.
    
    These arguments are optional and default to C{/dev/null}.
    Note that stderr is opened unbuffered, so if it shares a file with stdout
    then interleaved output may not appear in the order that you expect.
    """
    import os
    import sys
    
    # Do first fork.
    try: 
        pid = os.fork() 
        if pid > 0: sys.exit(0) # Exit first parent.
    except OSError, e: 
        sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)
        
    # Decouple from parent environment.
    os.chdir("/") 
    os.umask(0) 
    os.setsid() 
    
    # Do second fork.
    try: 
        pid = os.fork() 
        if pid > 0: sys.exit(0) # Exit second parent.
    except OSError, e: 
        sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)
    
    # Open file descriptors and print start message
    if not stderr:
        stderr = stdout
        
    si = file(stdin, 'r')
    so = file(stdout, 'a+')
    se = file(stderr, 'a+', 0)
    pid = str(os.getpid())
    if pidfile:
        f = file(pidfile,'w+')
        f.write("%s\n" % pid)
        f.close()
    
    # Redirect standard file descriptors.
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

def defaultLogging(level = logging.WARNING, logfile = None):
    """Establish default logging as used by the example scripts.

    If logfile is None (the default), log to stdout.
    Read the source for details."""

    log = logging.getLogger('')
    log.setLevel(level)
    log_formatter = logging.Formatter(
        '%(asctime)s %(levelname)-5s %(name)s %(message)s')
    if logfile is None:
        hdlr = logging.StreamHandler()
        hdlr.setFormatter(log_formatter)
        log.addHandler(hdlr)
    else:
        hdlr = logging.handlers.RotatingFileHandler(logfile,
                                                    maxBytes=1024 * 1024 * 4,
                                                    backupCount = 2)
        hdlr.setFormatter(log_formatter)
        log.addHandler(hdlr)
        
    return log

def set_TiNGtrace(option, opt, value, parser):
    """Helper function for the option parser: set TiNGtrace."""
    
    import lowlevel
    lowlevel.cvar.TiNGtrace = value

def defaultOptions(repeat = False, *args, **kwargs):
    """A default option parser.

    I{Related Python documentation:} U{optparse
    <http://docs.python.org/lib/module-optparse.html>}

    Passes all extra args/kwargs on to the OptionParser constructor.

    The returned option parser understands the following arguments:

     - -c CARD or --card=CARD: select card
     - -p PORT or --port=PORT: select port
     - -c MODULE or --module=MODULE: select module
     - -t TiNGtrace or --tingtrace=TiNGtrace: select TiNGtrace level (0-9)
     - -r or --repeat: repeat after hangup

    @param repeat: Include -r or --repeat in the option list. Off by default.

    @return: an option parser with the default options listed above.
    """

    parser = optparse.OptionParser(*args, **kwargs)
    parser.add_option('-p', '--port', action='store', type='int', default = 0,
                      help='use the specified port for PSTN calls')
    parser.add_option('-c', '--card', action='store', type='int', default = 0,
                      help='use the specified card')
    parser.add_option('-m', '--module', action='store', type='int',
                      default = 0, help='use the specified module for ' \
                      'speech and RTP channels')
    parser.add_option('-t', '--tingtrace', action='callback',
                      callback=set_TiNGtrace,
                      type='int', default = 0, help='Set TiNG trace level.')
    
    if repeat:
        parser.add_option('-r', '--repeat', action='store_true',
                          help='Repeat after hangup.')

    return parser

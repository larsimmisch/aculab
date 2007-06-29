"""Exception classes for the Aculab API.

Job termination reasons are also modelled as exceptions.
This is stretching the concept 'exception' a little, because some
are perfectly normal and to be expected.

But since exeptions due to an error may also occur, this seems better than to
create a distinction between expected causes and unexpected ones -
in particular because the distinction is arbitrary in some cases.

See StopIteration for a precedent.
"""

from names import error_names, sm_error_names, fax_error_names

class AculabError(Exception):
    """Call Control exception. The error code is stored in value."""
    
    def __init__(self, rc, function = '', name = None):
        self.name = name
        self.value = rc

        if function:
            if name:
                desc = '%s %s failed: ' % (name, function)
            else:
                desc = '%s() failed: ' % (function)
        else:
            if handle:
                desc = '[0x%x]: ' % handle
            else:
                desc = ''

        if rc in error_names.keys():
            desc = desc + error_names[rc]
        else:
            desc = desc + str(rc)
            
        self.desc = desc

    def __repr__(self):
        return self.desc

    def __str__(self):
        return self.desc

class AculabSpeechError(AculabError):
    """Prosody exception. The error code is stored in value."""
    
    def __init__(self, rc, function = ''):
        if rc in sm_error_names.keys():
            self.value = rc
            if function:
                self.desc = function + '() failed: ' + sm_error_names[rc]
            else:
                self.desc = sm_error_names[rc]
        else:
            if function:
                self.desc = function + '() failed: ' + str(rc)
            else:
                self.desc = 'unknown error: ' + str(rc)
            
class AculabFAXError(AculabError):
    """FAX exception. The error code is stored in value."""

    def __init__(self, rc, function = ''):
        if rc in fax_error_names.keys():
            self.value = rc
            if function:
                self.desc = function + '() failed: ' + fax_error_names[rc]
            else:
                self.desc = fax_error_names[rc]
        else:
            if function:
                self.desc = function + '() failed: ' + str(rc)
            else:
                self.desc = 'unknown error: ' + str(rc)

class AculabStopped(Exception):
    """Termination reason: stopped."""
    
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return 'stopped'

class AculabClosed(Exception):
    """Termination reason: closed."""
    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return 'closed'

class AculabSilence(Exception):
    """Termination reason: silence."""
    
    def __init__(self, silence = None):
        Exception.__init__(self)
        self.silence = silence

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        if self.silence:
            return 'silence(%.3fs)' % self.silence
        else:
            return 'silence'

class AculabTimeout(Exception):
    """Termination reason: timeout."""

    def __repr__(self):
        return 'timeout'

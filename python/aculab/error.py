from names import error_names, sm_error_names, fax_error_names

class AculabError(Exception):

    def __init__(self, rc, function = '', handle = None):
        self.handle = handle
        self.value = rc

        if function:
            if handle:
                desc = '[0x%x] %s failed: ' % (handle, function)
            else:
                desc = ' %s() failed: ' % (function)
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
        
    def __str__(self):
        return self.desc

class AculabSpeechError(AculabError):

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

# Reasons for termination. These are modelled as exceptions.
# This is stretching the concept 'exception' a little, because some
# are perfectly normal and to be expected.

# But since actual exeptions may also occur, this seems better than to
# create a distinction between expected causes and unexpected ones -
# in particular because the distinction is arbitrary in some cases.

# See also StopIteration for precedent.

class AculabCompleted(Exception):
    pass

class AculabStop(Exception):
    pass

class AculabClosed(Exception):
    pass

class AculabSilence(Exception):
    pass

class AculabTimeout(Exception):
    pass

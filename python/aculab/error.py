from names import error_names

class AculabError:

    def __init__(self, rc, function = ''):
        if rc in error_names.keys():
            self.value = rc
            if function:
                self.desc = function + '() failed: ' + error_names[rc]
            else:
                self.desc = error_names[rc]
        else:
            if function:
                self.desc = function + '() failed: ' + str(rc)
            else:
                self.desc = 'unknown error: ' + str(rc)
            
    def __str__(self):
        return self.desc

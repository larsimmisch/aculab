import sys
import getopt
import xml.sax
import xml.sax.handler

class FindStruct(xml.sax.handler.ContentHandler):

    def __init__(self, file = sys.stdout):
        self.in_class = 0
        self.in_typescope = 0
        self.in_cdecl = 0
        self.candidate = None
        self.locator = None
        self.file = file

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
                    self.file.write('SIZED_STRUCT(%s)\n' % self.candidate)

    def endElement(self, name):
        if name == 'class':
            self.candidate = None
            self.in_class = self.in_class - 1
        elif name == 'typescope':
            self.in_typescope = self.in_typescope - 1
        elif name == 'cdecl':
            self.in_cdecl = self.in_cdecl - 1

def usage():
    print 'sized_struct.py [-o outfile] <xmlfile>'
    sys.exit(-2)
    

if __name__ == '__main__':
    outfile = 'sized_struct.i'

    options, args = getopt.getopt(sys.argv[1:], 'o:')
    for o, a in options:
        if o == '-o':
            outfile = a
        else:
            usage()


if len(args) != 1:
    usage()

of = open(outfile, 'w')
parser = xml.sax.make_parser()
handler = FindStruct(of)

parser.setContentHandler(handler)
parser.parse(args[0])
of.close()

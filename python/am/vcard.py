#!/usr/bin/env python
import sys

sys.path.extend(['.', '..'])

import codecs
from vobject.base import readComponents

addresses = '/var/addresses/All.vcf'

def tel_type(tel):
    types = tel.params.get('TYPE', None)
    if types:
        for t in types:
            n = t.lower()
            if n == 'fax':
                return 'Fax'
            if n == 'cell':
                return 'Mobil'

    return 'Tel'

def tel_normalize(tel):
    for c in ('-', ' ', '\t'):
        tel = tel.replace(c, '')

    if tel[0] == '+':
        return tel

    if tel[0] != '0':
        return '+4940' + tel

    if tel[:2] == '00':
        return '+' + tel[2:]

    if tel[0] == '0':
        return '+49' + tel[1:]

    return tel

def vcard_str(vc):
    
    def join(val, n = '', c = ' '):
        if not val:
            return ''
        if type(val) == type([]):
            return c.join(val) + n
        return val + n

    fn = getattr(vc, 'fn', None)
    adr = getattr(vc, 'adr', None)
    tel = getattr(vc, 'tel_list', None)
    email = getattr(vc, 'email_list', None)

    s = fn.value + '\n'
    if adr:
        a = adr.value
        s = s + join(a.extended, '\n')
        s = s + join(a.street, '\n')
        if a.code or a.city:
            s = s + join(a.code, ' ')
            s = s + join(a.city)
            s = s + '\n'
        s = s + join(a.country, '\n')
    if tel:
        for t in tel:
            s = s + '%s: %s\n' % (
                tel_type(t), t.value)
    if email:
        for e in email:
            s = s + join('mailto:' + e.value, '\n')

    return s

def vcard_find(tel):
    f = codecs.open(addresses, 'r', encoding='UTF-8')
    try:
        vcards = readComponents(f)

        tel = tel_normalize(tel)
        for vc in vcards:
            t = getattr(vc, 'tel_list', None)
            if t:
                for i in t:
                    if tel == tel_normalize(i.value):
                        return vc
    finally:
        f.close()


if __name__ == '__main__':

    import sys

    if len(sys.argv) > 1:
        tel = sys.argv[1]
    else:
        tel = '3172541'

    vc = vcard_find(tel)
    print vcard_str(vc)



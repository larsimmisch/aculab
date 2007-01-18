import urllib
import logging
import threading

log = logging.getLogger('slim')

server = 'bernoulli'
players = [ '00:04:20:05:82:60', '00:04:20:02:05:47' ]

def slim_display(line1, line2, duration, player = None):
    url = 'http://%s:9000/status.txt?' % server
    if player:
        url = url + 'player=%s&' % urllib.quote(player)
        
    url = url + 'p0=display&p1=%s&p2=%s&p3=%.1f' % \
          (urllib.quote(line1), urllib.quote(line2), float(duration))

    log.debug(url)
    urllib.urlopen(url)

def cli_display(cli):
    line1 = 'Calling: %s' % cli
    line2 = ''
    try:
        from vcard import vcard_find, vcard_str, tel_normalize, tel_type

        vc = vcard_find(cli)
        if vc:
            line2 = vc.fn.value
            for t in vc.tel_list:
                if tel_normalize(cli) == tel_normalize(t.value):
                    line2 = '%s %s' % (line2, tel_type(t.params['TYPE']))

    except ImportError:
        pass
    except:
        log.warn('VCard lookup for CLI %s failed.', cli, exc_info=1)

    for p in players:
        slim_display(line1, line2, 20, p)

def async_cli_display(cli):
    t = threading.Thread(None, cli_display, 'slim display', cli)
    t.start()
    return t

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(message)s')
    
    cli_display('01772706491')
    

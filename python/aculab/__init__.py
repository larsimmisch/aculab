import logging

__all__ = ['_lowlevel', 'lowlevel', 'names', 'error',
           'busses', 'callcontrol', 'speech', 'Bus']

def defaultLogging(level = logging.WARNING):
    log = logging.getLogger('')
    log.setLevel(level)
    log_formatter = logging.Formatter(
        '%(asctime)s %(name)s %(levelname)-5s %(message)s')
    hdlr = logging.StreamHandler()
    hdlr.setFormatter(log_formatter)
    log.addHandler(hdlr)

    return log

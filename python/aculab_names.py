import re
import aculab

# build a map of EV_* constants
event = {}
_event_pattern = re.compile(r'EV_[A-Z_]+')

error = {}
_error_pattern = re.compile(r'ERR_[A-Z_]+')

for k in aculab.__dict__.keys():
    if _event_pattern.match(k):
        event[aculab.__dict__[k]] = k
    elif _error_pattern.match(k):
        error[aculab.__dict__[k]] = k

import re
import lowlevel

# build a map of EV_* constants
event_names = {}
ext_event_names = {}
_ext_pattern = re.compile(r'EV_EXT_[A-Z_]+')
_event_pattern = re.compile(r'EV_[A-Z_]+')

sm_error_names = {}
_sm_error_pattern = re.compile(r'ERR_SM_[A-Z_]+')

error_names = {}
_error_pattern = re.compile(r'ERR_[A-Z_]+')

for k in lowlevel.__dict__.keys():
    if _ext_pattern.match(k):
        ext_event_names[lowlevel.__dict__[k]] = k
    elif _event_pattern.match(k):
        event_names[lowlevel.__dict__[k]] = k
    elif _sm_error_pattern.match(k):
        sm_error_names[lowlevel.__dict__[k]] = k
    elif _error_pattern.match(k):
        error_names[lowlevel.__dict__[k]] = k

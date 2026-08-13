import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

# Strip only ASCII control characters (NUL, BEL, BS, VT, FF, SO-US, DEL).
# Allows all printable ASCII, Unicode, emojis, em-dash, newlines, and tabs —
# anything a human-readable diagnostic string might need.
_STRIP_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class Safe_Str__Doctor_Message(Safe_Str):
    regex             = _STRIP_CONTROLS
    max_length        = 4096
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = False

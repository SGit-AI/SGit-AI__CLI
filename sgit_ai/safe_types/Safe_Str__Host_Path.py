import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# A path on the user's machine, kept exactly (Windows drive letters, spaces, Unicode): any
# printable text, no control characters. Refused, never rewritten.
HOST_PATH__REGEX = re.compile(r'^[^\x00-\x1f\x7f]{0,4096}\Z')


class Safe_Str__Host_Path(Safe_Str):
    regex             = HOST_PATH__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 4096
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True

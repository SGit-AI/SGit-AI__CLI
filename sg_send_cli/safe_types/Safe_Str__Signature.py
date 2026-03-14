import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

SIGNATURE__REGEX      = re.compile(r'^[A-Za-z0-9+/=]{1,256}$')
SIGNATURE__MAX_LENGTH = 256

class Safe_Str__Signature(Safe_Str):
    regex             = SIGNATURE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = SIGNATURE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

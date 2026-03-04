import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

WRITE_KEY__REGEX      = re.compile(r'^[0-9a-f]{64}$')
WRITE_KEY__MAX_LENGTH = 64

class Safe_Str__Write_Key(Safe_Str):
    regex             = WRITE_KEY__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = WRITE_KEY__MAX_LENGTH
    exact_length      = True
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

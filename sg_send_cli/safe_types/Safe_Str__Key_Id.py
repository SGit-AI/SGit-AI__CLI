import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

KEY_ID__REGEX      = re.compile(r'^key-[0-9a-f]{8,64}$')
KEY_ID__MAX_LENGTH = 68

class Safe_Str__Key_Id(Safe_Str):
    regex             = KEY_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = KEY_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

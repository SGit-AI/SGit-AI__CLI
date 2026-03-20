import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

ENCRYPTED_VALUE__REGEX      = re.compile(r'^[A-Za-z0-9+/=]+$')
ENCRYPTED_VALUE__MAX_LENGTH = 1024

class Safe_Str__Encrypted_Value(Safe_Str):
    regex             = ENCRYPTED_VALUE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = ENCRYPTED_VALUE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

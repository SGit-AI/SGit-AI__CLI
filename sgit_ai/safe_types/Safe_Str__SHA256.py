import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

SHA256__REGEX      = re.compile(r'^[0-9a-f]{64}$')
SHA256__MAX_LENGTH = 64

class Safe_Str__SHA256(Safe_Str):
    regex             = SHA256__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = SHA256__MAX_LENGTH
    exact_length      = True
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

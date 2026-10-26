import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

SHA256_HEX__REGEX = re.compile(r'^[0-9a-f]{64}$')

class Safe_Str__Sha256_Hex(Safe_Str):
    regex             = SHA256_HEX__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 64
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

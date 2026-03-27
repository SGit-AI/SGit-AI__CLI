import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

SIMPLE_TOKEN__REGEX      = re.compile(r'^[a-z]+-[a-z]+-\d{4}$')
SIMPLE_TOKEN__MAX_LENGTH = 64

class Safe_Str__Simple_Token(Safe_Str):
    regex             = SIMPLE_TOKEN__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = SIMPLE_TOKEN__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

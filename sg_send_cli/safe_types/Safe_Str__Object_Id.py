import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

OBJECT_ID__REGEX      = re.compile(r'^[0-9a-f]{12}$')
OBJECT_ID__MAX_LENGTH = 12

class Safe_Str__Object_Id(Safe_Str):
    regex             = OBJECT_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = OBJECT_ID__MAX_LENGTH
    exact_length      = True
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

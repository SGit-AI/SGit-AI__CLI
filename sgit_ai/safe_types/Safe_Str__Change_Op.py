import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

CHANGE_OP__REGEX = re.compile(r'^[AMD]$')                 # added, modified, deleted

class Safe_Str__Change_Op(Safe_Str):
    regex             = CHANGE_OP__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 1
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

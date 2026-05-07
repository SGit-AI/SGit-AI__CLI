import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

RESTORE_MODE__REGEX      = re.compile(r'^(bare|expanded)$')
RESTORE_MODE__MAX_LENGTH = 8

class Safe_Str__Restore_Mode(Safe_Str):
    regex             = RESTORE_MODE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = RESTORE_MODE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

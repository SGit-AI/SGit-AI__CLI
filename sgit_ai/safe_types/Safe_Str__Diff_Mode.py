import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

DIFF_MODE__REGEX      = re.compile(r'^(head|remote|commit)$')
DIFF_MODE__MAX_LENGTH = 16

class Safe_Str__Diff_Mode(Safe_Str):
    regex             = DIFF_MODE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = DIFF_MODE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

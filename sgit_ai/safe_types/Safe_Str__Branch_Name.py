import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

BRANCH_NAME__REGEX      = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
BRANCH_NAME__MAX_LENGTH = 64

class Safe_Str__Branch_Name(Safe_Str):
    regex             = BRANCH_NAME__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = BRANCH_NAME__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

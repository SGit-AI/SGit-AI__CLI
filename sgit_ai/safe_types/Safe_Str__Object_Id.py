import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# format 1: 12 hex (48 bits); format 2: 32 hex (128 bits). Both may appear in one vault.
OBJECT_ID__REGEX      = re.compile(r'^obj-cas-imm-(?:[0-9a-f]{12}|[0-9a-f]{32})$')
OBJECT_ID__MAX_LENGTH = 44

class Safe_Str__Object_Id(Safe_Str):
    regex             = OBJECT_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = OBJECT_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

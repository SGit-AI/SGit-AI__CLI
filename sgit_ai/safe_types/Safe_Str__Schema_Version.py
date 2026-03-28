import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

SCHEMA_VERSION__REGEX      = re.compile(r'^[a-z_]+_v\d+$')
SCHEMA_VERSION__MAX_LENGTH = 64

class Safe_Str__Schema_Version(Safe_Str):
    regex             = SCHEMA_VERSION__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = SCHEMA_VERSION__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

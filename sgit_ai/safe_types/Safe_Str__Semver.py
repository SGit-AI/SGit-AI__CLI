import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# semver: major.minor.patch  e.g. "1.0.0"
class Safe_Str__Semver(Safe_Str):
    regex             = re.compile(r'^\d+\.\d+\.\d+$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 20
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

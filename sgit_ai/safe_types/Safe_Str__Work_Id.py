import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# UUID4 hex + hyphens, e.g. "550e8400-e29b-41d4-a716-446655440000"
class Safe_Str__Work_Id(Safe_Str):
    regex             = re.compile(r'^[a-f0-9\-]{8,36}$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 36
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

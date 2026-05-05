import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

class Safe_Str__Workflow_Name(Safe_Str):
    regex             = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 64
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

REF_ID__REGEX      = re.compile(r'^ref-[0-9a-f]{8,64}$')
REF_ID__MAX_LENGTH = 68

class Safe_Str__Ref_Id(Safe_Str):
    regex             = REF_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = REF_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

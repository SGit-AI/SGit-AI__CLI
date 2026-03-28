import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

TRANSFER_ID__REGEX      = re.compile(r'^[a-zA-Z0-9]{12}$')
TRANSFER_ID__MAX_LENGTH = 12

class Safe_Str__Transfer_Id(Safe_Str):
    regex             = TRANSFER_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = TRANSFER_ID__MAX_LENGTH
    exact_length      = True
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

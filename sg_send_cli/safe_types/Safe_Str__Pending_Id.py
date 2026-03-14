import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

PENDING_ID__REGEX      = re.compile(r'^pending-\d{1,20}_[0-9a-f]{8,32}$')
PENDING_ID__MAX_LENGTH = 60

class Safe_Str__Pending_Id(Safe_Str):
    regex             = PENDING_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = PENDING_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

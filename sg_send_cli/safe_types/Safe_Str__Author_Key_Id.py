import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

AUTHOR_KEY_ID__REGEX      = re.compile(r'^[a-zA-Z0-9:_\-]{1,128}$')
AUTHOR_KEY_ID__MAX_LENGTH = 128

class Safe_Str__Author_Key_Id(Safe_Str):
    regex             = AUTHOR_KEY_ID__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = AUTHOR_KEY_ID__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

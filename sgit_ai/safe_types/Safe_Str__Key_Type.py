import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

KEY_TYPE__REGEX      = re.compile(r'^(vault_key|none|pki|password)$')
KEY_TYPE__MAX_LENGTH = 16

class Safe_Str__Key_Type(Safe_Str):
    regex             = KEY_TYPE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = KEY_TYPE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

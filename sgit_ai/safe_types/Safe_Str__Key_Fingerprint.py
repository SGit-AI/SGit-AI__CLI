import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

KEY_FINGERPRINT__REGEX      = re.compile(r'^sha256:[0-9a-f]{16}$')
KEY_FINGERPRINT__MAX_LENGTH = 23

class Safe_Str__Key_Fingerprint(Safe_Str):
    regex             = KEY_FINGERPRINT__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = KEY_FINGERPRINT__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

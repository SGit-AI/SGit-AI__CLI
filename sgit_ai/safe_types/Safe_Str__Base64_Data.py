import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

BASE64_DATA__REGEX      = re.compile(r'^[A-Za-z0-9+/=]*$')
BASE64_DATA__MAX_LENGTH = 10 * 1024 * 1024                                    # 10 MB base64

class Safe_Str__Base64_Data(Safe_Str):
    regex             = BASE64_DATA__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = BASE64_DATA__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

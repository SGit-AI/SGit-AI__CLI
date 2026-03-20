import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

ISO_TIMESTAMP__REGEX      = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$')
ISO_TIMESTAMP__MAX_LENGTH = 30

class Safe_Str__ISO_Timestamp(Safe_Str):
    regex             = ISO_TIMESTAMP__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = ISO_TIMESTAMP__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

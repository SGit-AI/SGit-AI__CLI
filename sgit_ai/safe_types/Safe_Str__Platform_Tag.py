import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

PLATFORM_TAG__REGEX = re.compile(r'^[a-zA-Z0-9_.\-]{0,64}\Z')     # linux, darwin, windows, x86_64, arm64, 26.0.1 …


class Safe_Str__Platform_Tag(Safe_Str):
    regex             = PLATFORM_TAG__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 64
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

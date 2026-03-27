import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# Allow printable characters (ASCII and Unicode), tabs, newlines, and carriage returns.
# Unified diff output may contain Unicode from the diffed file content.
DIFF_TEXT__REGEX      = re.compile(r'^[\x20-\x7E\n\r\t\u0080-\U0010FFFF]*$')
DIFF_TEXT__MAX_LENGTH = 10 * 1024 * 1024   # 10 MB ceiling

class Safe_Str__Diff_Text(Safe_Str):
    regex             = DIFF_TEXT__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = DIFF_TEXT__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True

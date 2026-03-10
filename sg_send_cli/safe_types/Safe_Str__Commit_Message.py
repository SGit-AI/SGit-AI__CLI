import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

COMMIT_MESSAGE__REGEX      = re.compile(r'^[\x20-\x7E\n\r\t]*$')
COMMIT_MESSAGE__MAX_LENGTH = 500

class Safe_Str__Commit_Message(Safe_Str):
    regex             = COMMIT_MESSAGE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = COMMIT_MESSAGE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True

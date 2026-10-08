import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# Any text but control characters (newline and tab allowed). The tag object is
# encrypted as a whole, so the message is never visible to the host.
TAG_MESSAGE__REGEX      = re.compile(r'^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$')
TAG_MESSAGE__MAX_LENGTH = 4096


class Safe_Str__Tag_Message(Safe_Str):
    regex             = TAG_MESSAGE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = TAG_MESSAGE__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False
    strict_validation = True

import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

FEATURE__REGEX      = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
FEATURE__MAX_LENGTH = 40

class Safe_Str__Feature(Safe_Str):
    """A vault feature flag in the branch index, e.g. 'ids-128', 'signatures-required'."""
    regex             = FEATURE__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = FEATURE__MAX_LENGTH
    allow_empty       = False
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True

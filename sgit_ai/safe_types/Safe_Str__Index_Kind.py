import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

INDEX_KIND__REGEX = re.compile(r'^(commit|snapshot)$')     # an index pack describes a commit (a delta) or a snapshot (a head)

class Safe_Str__Index_Kind(Safe_Str):
    regex             = INDEX_KIND__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 8
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode


class Safe_Str__Hunk_Id(Safe_Str):
    """A hunk's content-derived id, `h-` + 12 hex (design__03 §3.3): a stale id cannot
    select the wrong hunk, it simply no longer exists."""
    regex             = re.compile(r'^h-[0-9a-f]{12}$')
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = 14
    allow_empty       = True
    trim_whitespace   = True
    strict_validation = True

import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Merge_Reason(Safe_Str):
    """Why a path fell back to a whole-file conflict ("binary", "too large for a line merge")."""
    regex           = re.compile(r'[^\x20-\x7E]')
    max_length      = 200
    allow_empty     = True
    trim_whitespace = True

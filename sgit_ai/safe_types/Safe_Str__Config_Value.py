import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Config_Value(Safe_Str):
    """A value read from the user's Git config for signing (a program, a file path, a
    command line). Kept as written, control characters replaced."""
    regex           = re.compile(r'[\x00-\x1f\x7f]')
    max_length      = 4096
    allow_empty     = True
    trim_whitespace = True

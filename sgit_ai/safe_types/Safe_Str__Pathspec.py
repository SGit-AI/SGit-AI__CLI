import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Pathspec(Safe_Str):
    """A path or glob as typed on `sgit commit -- <pathspec>`: any Unicode, `* ? [` kept
    (Safe_Str__File_Path would rewrite them); control characters refused by replacement."""
    regex           = re.compile(r'[\x00-\x1f\x7f]')
    max_length      = 4096
    allow_empty     = True
    trim_whitespace = False

import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Grep_Pattern(Safe_Str):
    """A grep / pickaxe pattern as typed: any printable text up to 1,000 characters, kept as it is
    (spaces too); a NUL is replaced."""
    regex           = re.compile(r'[\x00]')
    max_length      = 1000
    allow_empty     = True
    trim_whitespace = False

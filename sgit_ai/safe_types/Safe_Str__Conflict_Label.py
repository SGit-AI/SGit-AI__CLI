import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Conflict_Label(Safe_Str):
    """The text after a conflict marker. Built from vault data (branch names, commit
    subjects), so anything outside printable ASCII becomes `_`: a label can never start
    a new line or put a marker on a line of its own."""
    regex           = re.compile(r'[^\x20-\x7E]')
    max_length      = 80
    allow_empty     = True
    trim_whitespace = True

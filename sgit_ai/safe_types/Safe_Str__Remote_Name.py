import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Remote_Name(Safe_Str):
    regex             = re.compile(r'[^a-z0-9_\-]')
    max_length        = 64
    allow_empty       = False
    to_lower_case     = True

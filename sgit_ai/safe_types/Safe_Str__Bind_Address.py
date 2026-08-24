import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

BIND_ADDRESS__REGEX = re.compile(r'[^a-zA-Z0-9.\-:\[\]]')


class Safe_Str__Bind_Address(Safe_Str):
    regex           = BIND_ADDRESS__REGEX
    max_length      = 253
    allow_empty     = True
    trim_whitespace = True

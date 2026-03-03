import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

ACCESS_TOKEN__REGEX      = re.compile(r'[^a-zA-Z0-9\-_.]')
ACCESS_TOKEN__MAX_LENGTH = 2048

class Safe_Str__Access_Token(Safe_Str):
    regex       = ACCESS_TOKEN__REGEX
    max_length  = ACCESS_TOKEN__MAX_LENGTH
    allow_empty = True

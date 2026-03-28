import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

PEM_KEY__REGEX      = re.compile(r'[^\x20-\x7E\n\r\t]')
PEM_KEY__MAX_LENGTH = 8192

class Safe_Str__PEM_Key(Safe_Str):
    regex       = PEM_KEY__REGEX
    max_length  = PEM_KEY__MAX_LENGTH
    allow_empty = True

import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

SECRET_KEY__REGEX      = re.compile(r'[^a-zA-Z0-9_.\-]')
SECRET_KEY__MAX_LENGTH = 256

class Safe_Str__Secret_Key(Safe_Str):
    regex       = SECRET_KEY__REGEX
    max_length  = SECRET_KEY__MAX_LENGTH
    allow_empty = False

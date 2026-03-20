import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

CONTENT_TYPE__REGEX      = re.compile(r'[^a-zA-Z0-9/._+\-]')
CONTENT_TYPE__MAX_LENGTH = 256

class Safe_Str__Content_Type(Safe_Str):
    regex       = CONTENT_TYPE__REGEX
    max_length  = CONTENT_TYPE__MAX_LENGTH
    allow_empty = True

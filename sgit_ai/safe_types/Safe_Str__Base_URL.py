import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

BASE_URL__REGEX      = re.compile(r'[^a-zA-Z0-9:/._\-]')
BASE_URL__MAX_LENGTH = 2048

class Safe_Str__Base_URL(Safe_Str):
    regex       = BASE_URL__REGEX
    max_length  = BASE_URL__MAX_LENGTH
    allow_empty = True
